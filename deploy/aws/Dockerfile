FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY business_central_client ./business_central_client
COPY clickup_integration ./clickup_integration
COPY inspection_invoices ./inspection_invoices
COPY config ./config
COPY scripts ./scripts
COPY webhook_bridge ./webhook_bridge
COPY whatsapp_integration ./whatsapp_integration

EXPOSE 8000

CMD ["sh", "-c", "uvicorn webhook_bridge.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
