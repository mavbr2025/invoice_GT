FROM public.ecr.aws/lambda/python:3.11

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt --target ${LAMBDA_TASK_ROOT}

COPY clickup_integration ${LAMBDA_TASK_ROOT}/clickup_integration
COPY inspection_reports ${LAMBDA_TASK_ROOT}/inspection_reports
COPY inspection_app ${LAMBDA_TASK_ROOT}/inspection_app

CMD ["inspection_app.handler.lambda_handler"]
