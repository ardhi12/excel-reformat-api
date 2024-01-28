include .env

# -------------------- GCP General -------------------- #
gcp_set_project: 
	gcloud config set project $(gcp_project_id)

gcp_set_account: 
	gcloud config set account ${gcp_email_account}

gcp_config_list: 
	gcloud config list

gcp_auth_login: gcp_set_project gcp_set_account
	gcloud auth login

# -------------------- GCP Artifact Registry -------------------- #
gcp_create_repo_artifact:
	gcloud artifacts repositories create ${artifact_repo} \
		--repository-format=docker \
		--location=${location} \
		--async

gcp_auth_repo_artifact:
	gcloud auth configure-docker ${location}

# -------------------- GCP Cloud Run -------------------- #
gcp_deploy_run:
	gcloud run deploy ${docker_image} \
		--image=${location}/$(gcp_project_id)/${artifact_repo}/${docker_image}:${docker_image_tag} \
		--min-instances=1 \
		--region=${region} \
		--project=${gcp_project_id} \
		--allow-unauthenticated \
		--service-account=$(service_account) 

# -------------------- GCP API Gateway -------------------- #
gcp_create_api:
	gcloud api-gateway apis create ${api_id} \
	--project=${gcp_project_id} \
	--labels env=development,runner=cloud-run

gcp_create_api_config:
	gcloud api-gateway api-configs create ${api_config_id} \
	--api=${api_id} \
	--openapi-spec=gcp-config/openapi2.yaml \
	--backend-auth-service-account=$(service_account) \
	--project=${gcp_project_id} \
	--labels env=development

gcp_create_api_gateway:
	gcloud api-gateway gateways create ${gateway_id} \
	--api=${api_id} \
	--api-config=${api_config_id} \
	--location=${gateway_location} \
	--project=${gcp_project_id} \
	--labels env=development

gcp_enable_api:
	gcloud services enable ${private_api}

gcp_create_api_key:
	gcloud beta services api-keys create \
	--display-name=${key_id} \
	--api-target service=${private_api}

gcp_deploy_api_gateway: gcp_create_api gcp_create_api_config gcp_create_api_gateway gcp_enable_api gcp_create_api_key
		
# -------------------- Local Docker -------------------- #
docker_build:
	docker build \
	--platform linux/amd64 \
	-t ${location}/$(gcp_project_id)/${artifact_repo}/${docker_image}:${docker_image_tag} \
	-f ./docker/Dockerfile .

docker_run:
	docker run \
	-v "$(shell pwd)/cred/service_account.json":/app/credential.json \
	-v "$(shell pwd)/.env":/app/.env \
	--name ${project_slug}-container \
	-d -p 8080:8080 \
	${location}/$(gcp_project_id)/${artifact_repo}/${docker_image}:${docker_image_tag}

docker_stop:
	docker stop ${project_slug}-container && docker rm ${project_slug}-container

docker_push_image_to_repo_artifact: 
	docker push ${location}/$(gcp_project_id)/${artifact_repo}/${docker_image}:${docker_image_tag}