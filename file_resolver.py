"""Resolução de caminhos para uma raiz de conteúdo administrada pelo grupo."""
import os as os_a
import re as re_a
from urllib.parse import unquote as i_unquote

class ForbiddenError(Exception):
    """Caminho inseguro ou sem permissão de leitura."""

class NotFoundError(Exception):
    """Não há arquivo regular no caminho solicitado."""

class FileResolver:

    def i_init(self_a, root_a: str) -> None:
        self_a.root_a = os_a.path.realpath(root_a)
        if not os_a.path.isdir(self_a.root_a):
            raise ValueError('O diretório raiz não existe')

    # Associação ao protocolo nativo do Python.
    __init__ = i_init

    def i_inside_root(self_a, path_a: str) -> str:
        resolved_a = os_a.path.realpath(path_a)
        try:
            # commonpath compara componentes; startswith aceitaria www-secret.
            inside_a = os_a.path.commonpath([self_a.root_a, resolved_a]) == self_a.root_a
        except ValueError:
            # commonpath compara componentes; startswith aceitaria www-secret.
            inside_a = False
        if not inside_a:
            raise ForbiddenError('O caminho sai do diretório raiz')
        return resolved_a

    def i_resolve(self_a, raw_path_a: str) -> str:
        if re_a.search('%(?![0-9A-Fa-f]{2})', raw_path_a):
            raise ForbiddenError('Percent-encoding inválido')
        try:
            path_a = i_unquote(raw_path_a, encoding='utf-8', errors='strict')
        except UnicodeError as error_a:
            raise ForbiddenError('Caminho não é UTF-8 válido') from error_a
        # Barra invertida, NUL e ':' também bloqueiam caminhos especiais do Windows.
        if not path_a.startswith('/') or any((char_a in path_a for char_a in ('\x00', '\\', ':'))):
            raise ForbiddenError('Caminho proibido')
        candidate_a = self_a.i_inside_root(os_a.path.join(self_a.root_a, path_a.lstrip('/')))
        # O index também pode ser um symlink; validar novamente é indispensável.
        if os_a.path.isdir(candidate_a):
            candidate_a = self_a.i_inside_root(os_a.path.join(candidate_a, 'index.html'))
        if not os_a.path.isfile(candidate_a):
            raise NotFoundError('Arquivo não encontrado')
        return candidate_a
