kubectl port-forward service/qdrant-study 6333:6333 &
kubectl port-forward service/qdrant-study 6334:6334  &
kubectl port-forward service/qdrant-study 6335:6335  &
kubectl port-forward service/unstructured-study-service  8080:8000 &
kubectl port-forward svc/mongodb-study 27017:27017 &
kubectl port-forward svc/code-runner-service 9000:8000 &
kubectl port-forward --namespace default svc/rediss-master 6379:6379 &
kubectl port-forward deploy/prometheus-server 9090 &
kubectl port-forward grafana-5c944f4c5-dnhdn 3000 &
kubectl port-forward service/plantuml-service 9080:9080  &
kubectl get secret --namespace default grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo

