# Production Deployment Guide

## Overview

This guide covers deploying the AI GPU Cloud platform to production on Kubernetes with full observability, auto-scaling, and fault tolerance.

## Prerequisites

- Kubernetes cluster (1.28+) with GPU support
- kubectl configured
- Helm 3.x
- Docker registry access
- Domain name and SSL certificates

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Load Balancer (Ingress)                  │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
    ┌────▼────┐            ┌────▼────┐
    │  API    │            │  API    │
    │  Pod 1  │            │  Pod 2  │
    └────┬────┘            └────┬────┘
         │                       │
         └───────────┬───────────┘
                     │
    ┌────────────────┼────────────────┐
    │                │                │
┌───▼───┐      ┌────▼────┐      ┌───▼────┐
│ Redis │      │PostgreSQL│      │ Kafka  │
└───────┘      └─────────┘      └────────┘
```

## Step 1: Prepare Kubernetes Cluster

### Install NVIDIA GPU Operator

```bash
# Add NVIDIA Helm repository
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm repo update

# Install GPU operator
helm install --wait --generate-name \
  -n gpu-operator --create-namespace \
  nvidia/gpu-operator
```

### Verify GPU nodes

```bash
kubectl get nodes -o json | jq '.items[].status.capacity."nvidia.com/gpu"'
```

## Step 2: Create Namespace and Secrets

```bash
# Create namespace
kubectl create namespace ai-gpu-cloud

# Create database credentials
kubectl create secret generic db-credentials \
  --from-literal=username=postgres \
  --from-literal=password=YOUR_SECURE_PASSWORD \
  -n ai-gpu-cloud

# Create API keys
kubectl create secret generic api-keys \
  --from-literal=jwt-secret=YOUR_JWT_SECRET \
  --from-literal=admin-key=YOUR_ADMIN_KEY \
  -n ai-gpu-cloud
```

## Step 3: Deploy PostgreSQL with TimescaleDB

```yaml
# postgres-deployment.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: ai-gpu-cloud
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: timescale/timescaledb:latest-pg15
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: password
        - name: POSTGRES_DB
          value: gpu_cloud
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 100Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: ai-gpu-cloud
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

Apply:
```bash
kubectl apply -f postgres-deployment.yaml
```

## Step 4: Deploy Redis

```yaml
# redis-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: ai-gpu-cloud
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        volumeMounts:
        - name: redis-storage
          mountPath: /data
      volumes:
      - name: redis-storage
        persistentVolumeClaim:
          claimName: redis-pvc
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-pvc
  namespace: ai-gpu-cloud
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: ai-gpu-cloud
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
```

Apply:
```bash
kubectl apply -f redis-deployment.yaml
```

## Step 5: Deploy Main API

```yaml
# api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: ai-gpu-cloud
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: your-registry/ai-gpu-cloud:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          value: postgresql://$(DB_USER):$(DB_PASSWORD)@postgres:5432/gpu_cloud
        - name: REDIS_URL
          value: redis://redis:6379/0
        - name: DB_USER
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: username
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: password
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: ai-gpu-cloud
spec:
  selector:
    app: api
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
  namespace: ai-gpu-cloud
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

Apply:
```bash
kubectl apply -f api-deployment.yaml
```

## Step 6: Deploy Monitoring Stack

### Prometheus

```yaml
# prometheus-deployment.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: ai-gpu-cloud
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'api'
      kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
          - ai-gpu-cloud
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: api
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: ai-gpu-cloud
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:latest
        ports:
        - containerPort: 9090
        volumeMounts:
        - name: config
          mountPath: /etc/prometheus
        - name: storage
          mountPath: /prometheus
      volumes:
      - name: config
        configMap:
          name: prometheus-config
      - name: storage
        persistentVolumeClaim:
          claimName: prometheus-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: ai-gpu-cloud
spec:
  selector:
    app: prometheus
  ports:
  - port: 9090
    targetPort: 9090
```

### Grafana

```yaml
# grafana-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: ai-gpu-cloud
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grafana
  template:
    metadata:
      labels:
        app: grafana
    spec:
      containers:
      - name: grafana
        image: grafana/grafana:latest
        ports:
        - containerPort: 3000
        env:
        - name: GF_SECURITY_ADMIN_PASSWORD
          valueFrom:
            secretKeyRef:
              name: api-keys
              key: admin-key
---
apiVersion: v1
kind: Service
metadata:
  name: grafana
  namespace: ai-gpu-cloud
spec:
  selector:
    app: grafana
  ports:
  - port: 3000
    targetPort: 3000
```

Apply monitoring:
```bash
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml
```

## Step 7: Configure Ingress

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  namespace: ai-gpu-cloud
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - api.ai-gpu-cloud.com
    secretName: api-tls
  rules:
  - host: api.ai-gpu-cloud.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api
            port:
              number: 80
```

Apply:
```bash
kubectl apply -f ingress.yaml
```

## Step 8: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n ai-gpu-cloud

# Check services
kubectl get svc -n ai-gpu-cloud

# Check ingress
kubectl get ingress -n ai-gpu-cloud

# View logs
kubectl logs -f deployment/api -n ai-gpu-cloud

# Test API
curl https://api.ai-gpu-cloud.com/health
```

## Step 9: Configure Monitoring Alerts

Create AlertManager configuration for critical alerts:

```yaml
# alertmanager-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: alertmanager-config
  namespace: ai-gpu-cloud
data:
  alertmanager.yml: |
    route:
      receiver: 'slack'
      group_by: ['alertname', 'cluster']
      group_wait: 10s
      group_interval: 10s
      repeat_interval: 12h
    
    receivers:
    - name: 'slack'
      slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts'
        title: 'AI GPU Cloud Alert'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

## Step 10: Backup and Disaster Recovery

### Database Backups

```bash
# Create CronJob for daily backups
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: ai-gpu-cloud
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:15
            command:
            - /bin/sh
            - -c
            - pg_dump -h postgres -U postgres gpu_cloud | gzip > /backup/backup-\$(date +%Y%m%d).sql.gz
            volumeMounts:
            - name: backup
              mountPath: /backup
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: backup-pvc
          restartPolicy: OnFailure
EOF
```

## Monitoring and Maintenance

### Key Metrics to Monitor

1. **API Performance**
   - Request latency (P50, P95, P99)
   - Request rate
   - Error rate

2. **Autonomous Engine**
   - Decision frequency
   - Reward trend
   - Action distribution

3. **Infrastructure**
   - GPU utilization
   - Node health
   - Pod restart count

4. **Business Metrics**
   - Active jobs
   - Revenue per hour
   - Cost efficiency

### Scaling Guidelines

- **API Pods**: Scale based on CPU/memory (70-80% threshold)
- **Database**: Vertical scaling for PostgreSQL, read replicas for high load
- **Redis**: Redis Cluster for >10GB data
- **GPU Nodes**: Auto-scale based on queue depth and utilization

## Troubleshooting

### Common Issues

1. **Pods not starting**
   ```bash
   kubectl describe pod <pod-name> -n ai-gpu-cloud
   kubectl logs <pod-name> -n ai-gpu-cloud
   ```

2. **Database connection issues**
   ```bash
   kubectl exec -it deployment/api -n ai-gpu-cloud -- env | grep DATABASE
   ```

3. **GPU not detected**
   ```bash
   kubectl get nodes -o json | jq '.items[].status.capacity'
   ```

## Security Checklist

- [ ] Enable RBAC
- [ ] Use network policies
- [ ] Encrypt secrets at rest
- [ ] Enable audit logging
- [ ] Configure pod security policies
- [ ] Use private container registry
- [ ] Enable TLS for all services
- [ ] Regular security scans
- [ ] Implement rate limiting
- [ ] Configure firewall rules

## Performance Optimization

1. **Database**
   - Enable connection pooling
   - Create indexes on frequently queried columns
   - Use TimescaleDB compression

2. **API**
   - Enable response caching
   - Use async/await throughout
   - Implement request batching

3. **RL Agent**
   - Use GPU for model training
   - Batch state processing
   - Periodic checkpoint saving

## Cost Optimization

1. Use spot instances for non-critical workloads
2. Right-size pod resources
3. Enable cluster autoscaler
4. Use horizontal pod autoscaling
5. Implement pod disruption budgets
6. Schedule non-urgent tasks during off-peak hours

---

**Deployment Complete!** 🎉

Your autonomous AI GPU Cloud platform is now running in production.
