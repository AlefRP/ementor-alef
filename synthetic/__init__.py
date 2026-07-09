"""Simulação de dados do domínio Olist.

Não é lógica de negócio: são geradores que alimentam o lab — eventos para a
fila SQS (camada quente) e linhas para o RDS de origem (camada fria). Ficam
fora de ``src/`` de propósito, para não pesarem no gate de cobertura; ainda
assim passam por blue/isort/bandit, porque vão dentro do zip das Lambdas.

O vocabulário vive em ``olist.py`` e é compartilhado pelas duas camadas — é o
que permite a um ETL futuro unir eventos quentes e tabelas frias.
"""
