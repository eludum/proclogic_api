# proclogic

curl -fsSL <https://ollama.com/install.sh> | sh

ollama run llama3.1

docker run -d --network=host -v open-webui:/app/backend/data -e OLLAMA_BASE_URL=<http://127.0.0.1:11434> --name open-webui --restart always ghcr.io/open-webui/open-webui:main

<http://localhost:8080/ollama/docs>

<https://docs.openwebui.com/api/>
