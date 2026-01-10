FROM public.ecr.aws/lambda/python:3.13 AS builder

WORKDIR /asset

COPY requirements.txt .
RUN pip install -r requirements.txt -t .

COPY index.py .