"""Construção manual das respostas; nenhum módulo HTTP de servidor."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime
import os
from typing import BinaryIO, Iterator, Optional
REASONS = {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed', 417: 'Expectation Failed', 500: 'Internal Server Error', 505: 'HTTP Version Not Supported'}
MESSAGES = {400: 'Requisição malformada.', 403: 'Acesso proibido.', 404: 'Arquivo não encontrado.', 405: 'Método não permitido.', 417: 'Expectativa não suportada.', 500: 'Erro interno do servidor.', 505: 'Versão HTTP não suportada.'}
MIME_TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.pdf': 'application/pdf', '.svg': 'image/svg+xml; charset=utf-8', '.ico': 'image/x-icon', '.gif': 'image/gif'}

def format_http_date() -> str:
    # Nomes ingleses e GMT são independentes do locale da máquina.
    return format_datetime(datetime.now(timezone.utc), usegmt=True)

def guess_content_type(path: str) -> str:
    return MIME_TYPES.get(os.path.splitext(path)[1].lower(), 'application/octet-stream')

@dataclass
class HttpResponse:
    status: int
    headers: dict = field(default_factory=dict)
    body: bytes = b''
    head_only: bool = False
    file: Optional[BinaryIO] = None

    def to_head_bytes(self) -> bytes:
        lines = [f'HTTP/1.1 {self.status} {REASONS[self.status]}']
        lines.extend((f'{name}: {value}' for (name, value) in self.headers.items()))
        return ('\r\n'.join(lines) + '\r\n\r\n').encode('iso-8859-1')

    def body_bytes(self) -> Iterator[bytes]:
        # HEAD anuncia o mesmo tamanho de GET, mas não lê nem envia o corpo.
        if self.head_only:
            return
        if self.file is None:
            if self.body:
                yield self.body
            return
        # Só enviar o tamanho anunciado, mesmo se o arquivo crescer após fstat().
        remaining = int(self.headers['Content-Length'])
        while remaining:
            # Lê até 64 KiB por vez; yield entrega cada bloco ao envio no socket.
            chunk = self.file.read(min(65536, remaining))
            if not chunk:
                raise OSError('Arquivo foi truncado durante o envio')
            remaining -= len(chunk)
            yield chunk

    def close(self) -> None:
        if self.file is not None:
            self.file.close()

    @classmethod
    def error(cls, status: int, extra_headers: Optional[dict]=None) -> 'HttpResponse':
        body = f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{status} {REASONS[status]}</title><h1>{status}</h1><p>{MESSAGES[status]}</p></html>\n'.encode('utf-8')
        headers = {'Content-Length': str(len(body)), 'Content-Type': 'text/html; charset=utf-8'}
        headers.update(extra_headers or {})
        return cls(status, headers, body)
