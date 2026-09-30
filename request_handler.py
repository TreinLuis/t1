"""Converte uma requisição já delimitada em resposta ou arquivo aberto."""
import os as os_a
import stat as stat_a
from file_resolver import FileResolver, ForbiddenError, NotFoundError
from http_parser import HttpRequest
from http_response import HttpResponse, i_format_http_date, i_guess_content_type

class RequestHandler:

    def i_init(self_a, resolver_a: FileResolver, server_name_a: str) -> None:
        self_a.resolver_a = resolver_a
        self_a.server_name_a = server_name_a

    # Associação ao protocolo nativo do Python.
    __init__ = i_init

    def i_handle(self_a, request_a: HttpRequest) -> HttpResponse:
        if request_a.method_a not in ('GET', 'HEAD'):
            response_a = HttpResponse.i_error(405, {'Allow': 'GET, HEAD'})
        else:
            file_a = None
            try:
                path_a = self_a.resolver_a.i_resolve(request_a.path_a)
                file_a = open(path_a, 'rb')
                metadata_a = os_a.fstat(file_a.fileno())
                if not stat_a.S_ISREG(metadata_a.st_mode):
                    raise NotFoundError('O alvo não é um arquivo regular')
                response_a = HttpResponse(200, {'Content-Length': str(metadata_a.st_size), 'Content-Type': i_guess_content_type(path_a)}, file_a=file_a)
                # A resposta assume o descritor e o libera mesmo em HEAD ou falha de envio.
                file_a = None
            except (ForbiddenError, PermissionError):
                response_a = HttpResponse.i_error(403)
            except (NotFoundError, FileNotFoundError, NotADirectoryError, IsADirectoryError):
                response_a = HttpResponse.i_error(404)
            except OSError:
                response_a = HttpResponse.i_error(500)
            finally:
                if file_a is not None:
                    file_a.close()
        response_a.head_only_a = request_a.method_a == 'HEAD'
        response_a.headers_a.update({'Date': i_format_http_date(), 'Server': self_a.server_name_a})
        return response_a
