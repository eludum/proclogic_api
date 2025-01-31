# proclogic

# run ai backend locally

curl -fsSL <https://ollama.com/install.sh> | sh

ollama run llama3.1

<https://www.llama.com/docs/model-cards-and-prompt-formats/meta-llama-3/>

docker run -d --network=host -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=<http://127.0.0.1:11434> --name open-webui --restart always ghcr.io/open-webui/open-webui:main

<http://localhost:8080/ollama/docs>

<https://docs.openwebui.com/api/>

<https://huggingface.co/CohereForAI/c4ai-command-r-plus-08-2024>
<https://docs.cohere.com/docs/prompting-command-r>

<https://aistudio.google.com/app/apikey>

# to host on vercel

<https://vercel.com/templates/next.js/nextjs-fastapi-starter>

# flow

prompt (reduce to yes or no answer)

openai embeddingsmodel

<https://www.langchain.com/pricing-langsmith>

RAG:

- embedding model
- document
- prompt
- llm

# endpoints

- embed
- send mail
- slug endpoint (id)
- update database endpoint
- scrape endpoint

# frontend

- mini dashboard
- view id result
- bestanden

# build locally

docker build . -t proclogic-api -f Dockerfile
docker tag proclogic-api

# prod

docker-compose -f compose.yml -f compose.prod.yml up
