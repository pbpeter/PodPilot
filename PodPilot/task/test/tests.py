import subprocess
import time

import docker
import requests
from docker.errors import DockerException, ImageNotFound
from hstest import StageTest, CheckResult, dynamic_test
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException
from urllib3.exceptions import NewConnectionError, MaxRetryError

class DeploymentTest(StageTest):
    @dynamic_test(order=1)
    def test_docker_is_installed_and_running(self):
        """Verify Docker daemon is reachable."""
        try:
            docker_client = docker.from_env()
            docker_client.ping()
        except MaxRetryError as e:
            return CheckResult.wrong(
                f"Docker did not respond after several attempts. Ensure your container runtime is running. Details: {e}"
            )
        except NewConnectionError as e:
            return CheckResult.wrong(
                f"Cannot establish a connection to the Docker daemon. Make sure the service is up and reachable. Details: {e}"
            )
        except requests.exceptions.ConnectionError as e:
            return CheckResult.wrong(
                f"Docker daemon is not reachable (connection error). Start or reconnect your container runtime. Details: {e}"
            )
        except DockerException as e:
            return CheckResult.wrong(
                f"Docker client error. Check your Docker installation and background service. Details: {e}"
            )
        except requests.exceptions.RequestException as e:
            return CheckResult.wrong(
                f"Docker request failed. Verify connectivity to the daemon. Details: {e}"
            )
        return CheckResult.correct()

    @dynamic_test(order=2)
    def test_kubectl_is_available_and_configured(self):
        """Verify kubectl is installed and kubeconfig has an active context."""
        try:
            subprocess.run(['kubectl', 'version', '--client'],
                           capture_output=True, check=True, timeout=10)
        except FileNotFoundError:
            return CheckResult.wrong(
                "kubectl is not installed or not on PATH. Install it and ensure your environment can find it."
            )
        except subprocess.TimeoutExpired:
            return CheckResult.wrong(
                "kubectl invocation timed out. Check your environment and try again."
            )
        except subprocess.CalledProcessError as e:
            return CheckResult.wrong(
                f"kubectl returned a non-zero exit status ({e.returncode}). Validate your installation."
            )

        try:
            contexts, active = config.list_kube_config_contexts()
            if not contexts:
                return CheckResult.wrong(
                    "No Kubernetes contexts found in the configuration. Set up a context first."
                )
            if not active:
                return CheckResult.wrong(
                    "No active Kubernetes context is selected. Choose an appropriate context."
                )
        except ConfigException as e:
            return CheckResult.wrong(f"Could not read kubeconfig. Check configuration location and format. Details: {e}")
        return CheckResult.correct()

    @dynamic_test(order=3)
    def test_local_kubernetes_cluster_is_available_and_running(self):
        """Verify Kubernetes API is reachable and has at least one Ready node."""
        try:
            config.load_kube_config()
        except ConfigException as e:
            return CheckResult.wrong(
                f"Cannot load kubeconfig. Check the path and contents of your configuration. Details: {e}"
            )

        kube_client = client.CoreV1Api()
        try:
            nodes = kube_client.list_node().items
        except MaxRetryError as e:
            return CheckResult.wrong(
                f"Kubernetes API did not respond after multiple attempts when listing nodes. Ensure a cluster is available. Details: {e}"
            )
        except NewConnectionError as e:
            return CheckResult.wrong(
                f"Cannot establish a connection to the Kubernetes API. Ensure a cluster is available. Details: {e}"
            )
        except requests.exceptions.ConnectionError as e:
            return CheckResult.wrong(
                f"Connection error while contacting the Kubernetes API for nodes. Confirm network/access. Details: {e}"
            )
        except ApiException as e:
            status = getattr(e, "status", None)
            if status in (401, 403):
                return CheckResult.wrong(
                    f"Unauthorized or forbidden to access cluster resources (HTTP {status}). Check your credentials and context. Details: {e}"
                )
            return CheckResult.wrong(
                f"Kubernetes API returned an error (HTTP {status}) when listing nodes. Details: {e}"
            )

        if not nodes:
            return CheckResult.wrong(
                "No nodes reported by the cluster. Ensure the control plane is healthy and nodes are registered."
            )

        ready_nodes = [n for n in nodes if any(
            c.type == "Ready" and c.status == "True"
            for c in (n.status.conditions or [])
        )]

        if not ready_nodes:
            return CheckResult.wrong(
                "No Ready nodes detected. Investigate node status and readiness conditions."
            )
        return CheckResult.correct()

    @dynamic_test(order=4)
    def test_namespace_podpilot_exists(self):
        """Verify namespace 'podpilot' exists."""
        try:
            config.load_kube_config()
        except ConfigException as e:
            return CheckResult.wrong(
                f"Cannot load kubeconfig. Check configuration location and validity. Details: {e}"
            )

        try:
            kube_client = client.CoreV1Api()
            kube_client.read_namespace("podpilot")
        except MaxRetryError as e:
            return CheckResult.wrong(
                f"Kubernetes API did not respond after multiple attempts when reading namespace 'podpilot'. Ensure a cluster is available. Details: {e}"
            )
        except NewConnectionError as e:
            return CheckResult.wrong(
                f"Cannot establish a connection to the Kubernetes API when reading namespace 'podpilot'. Ensure a cluster is available. Details: {e}"
            )
        except requests.exceptions.ConnectionError as e:
            return CheckResult.wrong(
                f"Connection error while contacting the Kubernetes API for namespace 'podpilot'. Confirm network/access. Details: {e}"
            )
        except ApiException as e:
            if getattr(e, "status", None) == 404:
                return CheckResult.wrong("Namespace 'podpilot' not found")
            status = getattr(e, "status", None)
            return CheckResult.wrong(
                f"Error checking namespace 'podpilot' (HTTP {status}). Details: {e}"
            )
        return CheckResult.correct()

    @dynamic_test(order=5)
    def test_postgres_secrets_exist(self):
        """Verify Secret 'postgres-secrets' exists in podpilot namespace."""
        try:
            config.load_kube_config()
            kube_client = client.CoreV1Api()
            kube_client.read_namespaced_secret("postgres-secrets", "podpilot")
        except ApiException as e:
            if getattr(e, "status", None) == 404:
                return CheckResult.wrong("Secret 'postgres-secrets' not found in podpilot namespace")
            return CheckResult.wrong(f"Error checking secret: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=6)
    def test_django_secret_key_exists(self):
        """Verify Secret 'django-secret-key' exists in podpilot namespace."""
        try:
            config.load_kube_config()
            kube_client = client.CoreV1Api()
            kube_client.read_namespaced_secret("django-secret-key", "podpilot")
        except ApiException as e:
            if getattr(e, "status", None) == 404:
                return CheckResult.wrong("Secret 'django-secret-key' not found in podpilot namespace")
            return CheckResult.wrong(f"Error checking secret: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=7)
    def test_nginx_configmap_exists(self):
        """Verify ConfigMap 'task-manager-nginx-config' exists in podpilot namespace."""
        try:
            config.load_kube_config()
            kube_client = client.CoreV1Api()
            kube_client.read_namespaced_config_map("task-manager-nginx-config", "podpilot")
        except ApiException as e:
            if getattr(e, "status", None) == 404:
                return CheckResult.wrong("ConfigMap 'task-manager-nginx-config' not found in podpilot namespace")
            return CheckResult.wrong(f"Error checking configmap: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()


    @dynamic_test(order=8)
    def test_postgres_service_exists(self):
        """Verify Postgres Service exists in podpilot namespace."""
        try:
            config.load_kube_config()
            kube_client = client.CoreV1Api()
            services = kube_client.list_namespaced_service("podpilot").items

            postgres_service = None
            for svc in services:
                if 'postgres' in svc.metadata.name.lower():
                    postgres_service = svc
                    break

            if not postgres_service:
                return CheckResult.wrong("Service for Postgres database not found in podpilot namespace.")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking service: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=9)
    def test_postgres_statefulset_exists_and_healthy(self):
        """Verify Postgres StatefulSet exists, is available, and mounts persistent storage."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            core_client = client.CoreV1Api()

            statefulsets = apps_client.list_namespaced_stateful_set("podpilot").items

            postgres_sts = None
            for sts in statefulsets:
                if 'postgres' in sts.metadata.name.lower():
                    postgres_sts = sts
                    break

            if not postgres_sts:
                return CheckResult.wrong("No StatefulSet for Postgres found in podpilot namespace.")

            # Check if StatefulSet is ready
            if postgres_sts.status.ready_replicas != postgres_sts.spec.replicas:
                return CheckResult.wrong(
                    f"Postgres StatefulSet not ready: {postgres_sts.status.ready_replicas}/{postgres_sts.spec.replicas} replicas ready"
                )

            # Check if it has volume claim templates (persistent storage)
            if not postgres_sts.spec.volume_claim_templates:
                return CheckResult.wrong("Postgres StatefulSet does not have persistent volume claims")

            # Check if it references postgres-secrets
            containers = postgres_sts.spec.template.spec.containers
            has_secret_ref = False
            for container in containers:
                if container.env:
                    for env_var in container.env:
                        if env_var.value_from and env_var.value_from.secret_key_ref:
                            if env_var.value_from.secret_key_ref.name == 'postgres-secrets':
                                has_secret_ref = True
                                break
                if container.env_from:
                    for env_from in container.env_from:
                        if env_from.secret_ref and env_from.secret_ref.name == 'postgres-secrets':
                            has_secret_ref = True
                            break

            if not has_secret_ref:
                return CheckResult.wrong("Postgres StatefulSet does not reference 'postgres-secrets' Secret")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking StatefulSet: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=10)
    def test_migration_job_completed_successfully(self):
        """Verify Django migration Job exists, completed successfully, and reads DB settings from Secrets."""
        try:
            config.load_kube_config()
            batch_client = client.BatchV1Api()

            jobs = batch_client.list_namespaced_job("podpilot").items

            migration_job = None
            for job in jobs:
                if 'migration' in job.metadata.name.lower() or 'migrate' in job.metadata.name.lower():
                    migration_job = job
                    break

            if not migration_job:
                return CheckResult.wrong("No migration Job found in podpilot namespace")

            # Check if Job completed successfully
            if not migration_job.status.succeeded or migration_job.status.succeeded < 1:
                if migration_job.status.failed:
                    return CheckResult.wrong(f"Migration Job failed: {migration_job.status.failed} failed pods")
                return CheckResult.wrong("Migration Job has not completed successfully")

            # Check if it references secrets (postgres-secrets or django-secret-key)
            containers = migration_job.spec.template.spec.containers
            has_secret_ref = False
            for container in containers:
                if container.env:
                    for env_var in container.env:
                        if env_var.value_from and env_var.value_from.secret_key_ref:
                            secret_name = env_var.value_from.secret_key_ref.name
                            if 'postgres' in secret_name or 'django' in secret_name:
                                has_secret_ref = True
                                break
                if container.env_from:
                    for env_from in container.env_from:
                        if env_from.secret_ref:
                            secret_name = env_from.secret_ref.name
                            if 'postgres' in secret_name or 'django' in secret_name:
                                has_secret_ref = True
                                break

            if not has_secret_ref:
                return CheckResult.wrong("Migration Job does not reference database Secrets")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking Job: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()


    @dynamic_test(order=11)
    def test_task_manager_service_exists(self):
        """Verify Service 'task-manager' exists and exposes port 80."""
        try:
            config.load_kube_config()
            kube_client = client.CoreV1Api()
            service = kube_client.read_namespaced_service("task-manager", "podpilot")

            # Check if service exposes port 80
            has_port_80 = False
            for port in service.spec.ports:
                if port.port == 80:
                    has_port_80 = True
                    break

            if not has_port_80:
                return CheckResult.wrong("Service 'task-manager' does not expose port 80")

        except ApiException as e:
            if getattr(e, "status", None) == 404:
                return CheckResult.wrong("Service 'task-manager' not found in podpilot namespace")
            return CheckResult.wrong(f"Error checking service: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=12)
    def test_task_manager_deployment_exists(self):
        """Verify Deployment 'task-manager' exists with two replicas and matching labels/selectors."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            deployment = apps_client.read_namespaced_deployment("task-manager", "podpilot")

            # Check if deployment has 2 replicas
            if deployment.spec.replicas != 2:
                return CheckResult.wrong(f"Deployment should have 2 replicas, found {deployment.spec.replicas}")

            # Check if deployment is ready
            if deployment.status.ready_replicas != 2:
                return CheckResult.wrong(
                    f"Deployment not ready: {deployment.status.ready_replicas}/2 replicas ready. Check with: \n"
                    f"kubectl get deploy -n podpilot \n"
                    f"kubectl get pods -n podpilot"
                    f"kubectl logs <pod-name> -n podpilot --all-containers=true"
                )

            # Check if labels and selectors match
            if not deployment.spec.selector or not deployment.spec.selector.match_labels:
                return CheckResult.wrong("Deployment does not have selector labels")

            pod_labels = deployment.spec.template.metadata.labels
            selector_labels = deployment.spec.selector.match_labels

            for key, value in selector_labels.items():
                if key not in pod_labels or pod_labels[key] != value:
                    return CheckResult.wrong("Deployment selector labels do not match pod labels")

        except ApiException as e:
            if getattr(e, "status", None) == 404:
                return CheckResult.wrong("Deployment 'task-manager' not found in podpilot namespace")
            return CheckResult.wrong(f"Error checking deployment: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=13)
    def test_deployment_has_init_container(self):
        """Verify Deployment has init container for collectstatic with shared emptyDir volume."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            deployment = apps_client.read_namespaced_deployment("task-manager", "podpilot")

            # Check if deployment has init containers
            if not deployment.spec.template.spec.init_containers:
                return CheckResult.wrong("Deployment does not have init containers")

            # Check for collectstatic in init container command
            has_collectstatic = False
            for init_container in deployment.spec.template.spec.init_containers:
                if init_container.command or init_container.args:
                    command_str = ' '.join(init_container.command or []) + ' '.join(init_container.args or [])
                    if 'collectstatic' in command_str:
                        has_collectstatic = True
                        break

            if not has_collectstatic:
                return CheckResult.wrong("Init container does not run collectstatic")

            # Check for emptyDir volume
            has_empty_dir = False
            if deployment.spec.template.spec.volumes:
                for volume in deployment.spec.template.spec.volumes:
                    if volume.empty_dir:
                        has_empty_dir = True
                        break

            if not has_empty_dir:
                return CheckResult.wrong("Deployment does not have emptyDir volume for static files")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking deployment: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=14)
    def test_deployment_has_sidecar_pattern(self):
        """Verify Deployment has Django main container on port 8000 and Nginx as an initContainer sidecar (restartPolicy Always) on port 80."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            deployment = apps_client.read_namespaced_deployment("task-manager", "podpilot")

            containers = deployment.spec.template.spec.containers
            init_containers = deployment.spec.template.spec.init_containers or []

            # Check for Django main container on port 8000
            has_django = False
            for container in containers:
                if container.ports:
                    for port in container.ports:
                        if port.container_port == 8000:
                            has_django = True
                            break

            if not has_django:
                return CheckResult.wrong("No main container exposing port 8000 (Django) found")

            # Check for Nginx sidecar as an initContainer with restartPolicy Always and port 80
            nginx_sidecar = None
            for init_container in init_containers:
                if 'nginx' in (init_container.image or '').lower() or 'nginx' in init_container.name.lower():
                    nginx_sidecar = init_container
                    break

            if not nginx_sidecar:
                return CheckResult.wrong(
                    "No Nginx initContainer sidecar found. "
                    "Nginx should be defined as an initContainer with restartPolicy Always to act as a sidecar."
                )

            # Check restartPolicy is Always (makes it a sidecar)
            restart_policy = getattr(nginx_sidecar, 'restart_policy', None)
            if not restart_policy or restart_policy.lower() != 'always':
                return CheckResult.wrong(
                    f"Nginx initContainer sidecar must have restartPolicy 'Always' to be a sidecar, "
                    f"found: '{restart_policy}'"
                )

            # Check Nginx sidecar exposes port 80
            has_port_80 = False
            if nginx_sidecar.ports:
                for port in nginx_sidecar.ports:
                    if port.container_port == 80:
                        has_port_80 = True
                        break

            if not has_port_80:
                return CheckResult.wrong("Nginx initContainer sidecar does not expose port 80")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking deployment: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()



    @dynamic_test(order=15)
    def test_deployment_images_and_volumes(self):
        """Verify Deployment image (task-manager:latest), volumeMounts at /app/staticfiles, shared emptyDir, and Nginx configmap mount."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            deployment = apps_client.read_namespaced_deployment("task-manager", "podpilot")

            containers = deployment.spec.template.spec.containers
            volumes = deployment.spec.template.spec.volumes

            # 1. Check deployment image (task-manager:latest)
            has_task_manager_image = False
            for container in containers:
                if container.image == "task-manager:latest":
                    has_task_manager_image = True
                    # 2. Check volumeMounts at /app/staticfiles for this container
                    has_static_mount = False
                    if container.volume_mounts:
                        for mount in container.volume_mounts:
                            if mount.mount_path == "/app/staticfiles":
                                has_static_mount = True
                                break
                    if not has_static_mount:
                        return CheckResult.wrong("Container with 'task-manager:latest' does not have volumeMount at /app/staticfiles")
                    break
            
            if not has_task_manager_image:
                return CheckResult.wrong("Deployment does not have a container with image 'task-manager:latest'")

            # 3. Check shared emptyDir volume
            has_empty_dir = False
            if volumes:
                for volume in volumes:
                    if volume.empty_dir is not None:
                        has_empty_dir = True
                        break
            if not has_empty_dir:
                return CheckResult.wrong("Deployment does not have a shared emptyDir volume")

            # 4. Check configmap mount task-manager-nginx-config
            has_configmap_mount = False
            if volumes:
                for volume in volumes:
                    if volume.config_map and volume.config_map.name == "task-manager-nginx-config":
                        has_configmap_mount = True
                        break
            if not has_configmap_mount:
                return CheckResult.wrong("Deployment does not have a volume for 'task-manager-nginx-config' ConfigMap")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking deployment: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=16)
    def test_deployment_uses_secrets(self):
        """Verify Deployment reads sensitive values from Secrets via secretKeyRef."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            deployment = apps_client.read_namespaced_deployment("task-manager", "podpilot")

            containers = deployment.spec.template.spec.containers

            has_django_secret = False
            has_postgres_secret = False

            for container in containers:
                if container.env:
                    for env_var in container.env:
                        if env_var.value_from and env_var.value_from.secret_key_ref:
                            secret_name = env_var.value_from.secret_key_ref.name
                            if 'django' in secret_name:
                                has_django_secret = True
                            if 'postgres' in secret_name:
                                has_postgres_secret = True

            if not has_django_secret:
                return CheckResult.wrong("Deployment does not reference 'django-secret-key' Secret")

            if not has_postgres_secret:
                return CheckResult.wrong("Deployment does not reference 'postgres-secrets' Secret")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking deployment: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=17)
    def test_deployment_has_resource_limits(self):
        """Verify Deployment has resource requests/limits for Django and Nginx containers."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            deployment = apps_client.read_namespaced_deployment("task-manager", "podpilot")

            containers = deployment.spec.template.spec.containers

            for container in containers:
                if not container.resources:
                    return CheckResult.wrong(f"Container '{container.name}' does not have resource specifications")

                if not container.resources.requests:
                    return CheckResult.wrong(f"Container '{container.name}' does not have resource requests")

                if not container.resources.limits:
                    return CheckResult.wrong(f"Container '{container.name}' does not have resource limits")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking deployment: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()

    @dynamic_test(order=18)
    def test_deployment_has_probes(self):
        """Verify Deployment has readiness and liveness probes for Django and Nginx containers."""
        try:
            config.load_kube_config()
            apps_client = client.AppsV1Api()
            deployment = apps_client.read_namespaced_deployment("task-manager", "podpilot")

            containers = deployment.spec.template.spec.containers

            for container in containers:
                if not container.readiness_probe:
                    return CheckResult.wrong(f"Container '{container.name}' does not have readiness probe")

                if not container.liveness_probe:
                    return CheckResult.wrong(f"Container '{container.name}' does not have liveness probe")

        except ApiException as e:
            return CheckResult.wrong(f"Error checking deployment: {e}")
        except ConfigException as e:
            return CheckResult.wrong(f"Cannot load kubeconfig: {e}")
        return CheckResult.correct()


    @dynamic_test(order=19)
    def test_forwarded_port_and_endpoints(self):
        """Verify that app is available on localhost:8080/api and localhost:8080/health (port-forward assumed pre-run)."""
        base_url = 'http://127.0.0.1:8080'

        # Give a short grace period for students who just started port-forwarding
        deadline = time.time() + 2
        last_error = None
        ready = False
        while time.time() < deadline:
            try:
                r = requests.head(base_url, timeout=2)
                ready = True
                break
            except Exception as e:
                last_error = e
                time.sleep(1)

        if not ready:
            return CheckResult.wrong(
                "Port 8080 is not reachable on localhost. Ensure you've run the "
                "kubectl port-forward command.\n"
                f"Last error: {last_error}"
            )

        try:
            resp_api = requests.get(f"{base_url}/api", timeout=5)
        except Exception as e:
            return CheckResult.wrong(f"Failed to reach {base_url}/api: {e}")
        if resp_api.status_code != 200:
            return CheckResult.wrong(
                f"/api endpoint returned unexpected status: {resp_api.status_code}. Body: {resp_api.text[:200]}"
            )

        try:
            resp_health = requests.get(f"{base_url}/health", timeout=5)
        except Exception as e:
            return CheckResult.wrong(f"Failed to reach {base_url}/health: {e}")
        if resp_health.status_code != 200:
            return CheckResult.wrong(
                f"/health endpoint returned unexpected status: {resp_health.status_code}. Body: {resp_health.text[:200]}"
            )

        return CheckResult.correct()


if __name__ == '__main__':
    DeploymentTest().run_tests()
