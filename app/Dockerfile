FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the model into the image so the app starts without network access.
ARG MODEL_NAME=Salesforce/blip-image-captioning-base
ENV MODEL_NAME=${MODEL_NAME}
RUN python -c "import os; from transformers import BlipProcessor, BlipForConditionalGeneration as M; \
n=os.environ['MODEL_NAME']; BlipProcessor.from_pretrained(n); M.from_pretrained(n)"
ENV HF_HUB_OFFLINE=1

COPY . .

# 8501 = Streamlit UI, 8000 = Prometheus /metrics
EXPOSE 8501 8000
# run.py starts /metrics and the model load, then launches `streamlit run app.py`.
CMD ["python", "run.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.maxUploadSize=500", "--server.fileWatcherType=none", \
     "--browser.gatherUsageStats=false"]
