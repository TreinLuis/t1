"""Converte uma requisição já delimitada em resposta ou arquivo aberto."""
import os
import stat
from file_resolver import FileResolver, ForbiddenError, NotFoundError
from http_parser import HttpRequest
from http_response import HttpResponse, format_http_date, guess_content_type

class RequestHandler:

    def __init__(self, resolver: FileResolver, server_name: str) -> None:
        self.resolver = resolver
        self.server_name = server_name

    def handle(self, request: HttpRequest) -> HttpResponse:
        if request.method not in ('GET', 'HEAD'):
            response = HttpResponse.error(405, {'Allow': 'GET, HEAD'})
        else:
            file = None
            try:
                path = self.resolver.resolve(request.path)
                file = open(path, 'rb')
                metadata = os.fstat(file.fileno())
                if not stat.S_ISREG(metadata.st_mode):
                    raise NotFoundError('O alvo não é um arquivo regular')
                response = HttpResponse(200, {'Content-Length': str(metadata.st_size), 'Content-Type': guess_content_type(path)}, file=file)
                # A resposta assume o descritor e o libera mesmo em HEAD ou falha de envio.
                file = None
            except (ForbiddenError, PermissionError):
                response = HttpResponse.error(403)
            except (NotFoundError, FileNotFoundError, NotADirectoryError, IsADirectoryError):
                response = HttpResponse.error(404)
            except OSError:
                response = HttpResponse.error(500)
            finally:
                if file is not None:
                    file.close()
        response.head_only = request.method == 'HEAD'
        response.headers.update({'Date': format_http_date(), 'Server': self.server_name})
        return response
