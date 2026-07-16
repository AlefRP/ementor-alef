"""Recurso de eventos: recebe o lote e o entrega à fila da camada quente."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool

from src.hot.api_events.core.configs import Settings, obter_configuracoes
from src.hot.api_events.core.deps import obter_cliente_sqs
from src.hot.api_events.core.messaging import publicar_eventos
from src.hot.api_events.schemas.event_schema import LoteDeEventos, RespostaPublicacao

router = APIRouter()


@router.post(
    '',
    response_model=RespostaPublicacao,
    status_code=status.HTTP_202_ACCEPTED,
    summary='Publica um lote de eventos de pedido na fila',
)
async def publicar(
    lote: LoteDeEventos,
    requisicao: Request,
    cliente: Annotated[object, Depends(obter_cliente_sqs)],
    configuracoes: Annotated[Settings, Depends(obter_configuracoes)],
) -> RespostaPublicacao:
    """202: o evento foi aceito e enfileirado — o processamento é assíncrono.

    O boto3 é síncrono; a publicação vai para o threadpool para não bloquear o
    event loop enquanto o SQS responde.
    """
    eventos = [evento.model_dump(mode='json') for evento in lote.events]
    try:
        publicados = await run_in_threadpool(
            publicar_eventos, cliente, configuracoes.QUEUE_URL, eventos
        )
    except Exception as erro:
        # O produtor precisa saber que NADA foi aceito para poder repetir o
        # lote; 502 distingue falha da fila de erro de contrato (422).
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='Falha ao publicar os eventos na fila.',
        ) from erro
    return RespostaPublicacao(
        published=publicados, correlation_id=requisicao.state.correlation_id
    )
