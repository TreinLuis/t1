"""Construção manual das respostas; nenhum módulo HTTP de servidor."""
from dataclasses import dataclass as i_dataclass, field as i_field
from datetime import datetime as i_datetime, timezone as i_timezone
from email.utils import format_datetime as i_format_datetime
import os as os_a
from typing import BinaryIO, Iterator, Optional
REASONS_a = {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed', 417: 'Expectation Failed', 500: 'Internal Server Error', 505: 'HTTP Version Not Supported'}
MESSAGES_a = {400: 'Requisição malformada.', 403: 'Acesso proibido.', 404: 'Arquivo não encontrado.', 405: 'Método não permitido.', 417: 'Expectativa não suportada.', 500: 'Erro interno do servidor.', 505: 'Versão HTTP não suportada.'}
MIME_TYPES_a = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.pdf': 'application/pdf', '.svg': 'image/svg+xml; charset=utf-8', '.ico': 'image/x-icon', '.gif': 'image/gif'}

def i_format_http_date() -> str:
    # Nomes ingleses e GMT são independentes do locale da máquina.
    return i_format_datetime(i_datetime.now(i_timezone.utc), usegmt=True)

def i_guess_content_type(path_a: str) -> str:
    return MIME_TYPES_a.get(os_a.path.splitext(path_a)[1].lower(), 'application/octet-stream')

@i_dataclass
class HttpResponse:
    status_a: int
    headers_a: dict = i_field(default_factory=dict)
    body_a: bytes = b''
    head_only_a: bool = False
    file_a: Optional[BinaryIO] = None

    def i_to_head_bytes(self_a) -> bytes:
        lines_a = [f'HTTP/1.1 {self_a.status_a} {REASONS_a[self_a.status_a]}']
        lines_a.extend((f'{name_a}: {value_a}' for (name_a, value_a) in self_a.headers_a.items()))
        return ('\r\n'.join(lines_a) + '\r\n\r\n').encode('iso-8859-1')

    def i_body_bytes(self_a) -> Iterator[bytes]:
        if self_a.head_only_a:
            return
        if self_a.file_a is None:
            if self_a.body_a:
                yield self_a.body_a
            return
        # Só enviar o tamanho anunciado, mesmo se o arquivo crescer após fstat().
        remaining_a = int(self_a.headers_a['Content-Length'])
        while remaining_a:
            chunk_a = self_a.file_a.read(min(65536, remaining_a))
            if not chunk_a:
                raise OSError('Arquivo foi truncado durante o envio')
            remaining_a -= len(chunk_a)
            yield chunk_a

    def i_close(self_a) -> None:
        if self_a.file_a is not None:
            self_a.file_a.close()

    @classmethod
    def i_error(cls_a, status_a: int, extra_headers_a: Optional[dict]=None) -> 'HttpResponse':
        body_a = f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{status_a} {REASONS_a[status_a]}</title><h1>{status_a}</h1><p>{MESSAGES_a[status_a]}</p></html>\n'.encode('utf-8')
        headers_a = {'Content-Length': str(len(body_a)), 'Content-Type': 'text/html; charset=utf-8'}
        headers_a.update(extra_headers_a or {})
        return cls_a(status_a, headers_a, body_a)
