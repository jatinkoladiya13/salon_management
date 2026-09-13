                    AWS
                     │
          ┌──────────┴──────────┐
          │                     │
         EC2                    S3
          │                  Media/Files
          │
    ┌─────┼─────┐
    │     │     │
 Django  Celery Beat
    │
    ├───────────────┐
    │               │
   RDS           Redis
PostgreSQL    ElastiCache


And we'll cover your requested AWS topics:

EC2 → Django/DRF deployment
RDS → PostgreSQL
S3 → media/static/file storage
Lambda → serverless task/example
Redis → eventually managed Redis/ElastiCache
Celery → background jobs
Daphne/Channels → WebSockets
Nginx → reverse proxy
HTTPS/SSL
GitHub Actions → automatic deployment


ssh -i ".\salon-management-key.pem" ubuntu@13.233.100.172
cd ~/salon_management

docker compose logs -f web
docker compose logs -f worker

docker compose exec web python manage.py shell

nano .env

ls -la | grep .env

cat .env