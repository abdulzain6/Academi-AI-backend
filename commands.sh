kubectl port-forward service/qdrant-study 6333:6333 &
kubectl port-forward service/qdrant-study 6334:6334  &
kubectl port-forward service/qdrant-study 6335:6335  &
kubectl port-forward service/unstructured-study-service  8080:8000 &
kubectl port-forward svc/mongodb-study 27017:27017 &
kubectl port-forward svc/code-runner-service 8000:8000
