"""Resolução de caminhos para uma raiz de conteúdo administrada pelo grupo."""
import os
import re
from urllib.parse import unquote

class ForbiddenError(Exception):
    """Caminho inseguro ou sem permissão de leitura."""

class NotFoundError(Exception):
    """Não há arquivo regular no caminho solicitado."""

class FileResolver:

    def __init__(self, root: str) -> None:
        self.root = os.path.realpath(root)
        if not os.path.isdir(self.root):
            raise ValueError('O diretório raiz não existe')

    def _inside_root(self, path: str) -> str:
        resolved = os.path.realpath(path)
        try:
            # commonpath compara componentes; startswith aceitaria www-secret.
            inside = os.path.commonpath([self.root, resolved]) == self.root
        except ValueError:
            # commonpath compara componentes; startswith aceitaria www-secret.
            inside = False
        if not inside:
            raise ForbiddenError('O caminho sai do diretório raiz')
        return resolved

    def resolve(self, raw_path: str) -> str:
        if re.search('%(?![0-9A-Fa-f]{2})', raw_path):
            raise ForbiddenError('Percent-encoding inválido')
        try:
            path = unquote(raw_path, encoding='utf-8', errors='strict')
        except UnicodeError as error:
            raise ForbiddenError('Caminho não é UTF-8 válido') from error
        # Barra invertida, NUL e ':' também bloqueiam caminhos especiais do Windows.
        if not path.startswith('/') or any((char in path for char in ('\x00', '\\', ':'))):
            raise ForbiddenError('Caminho proibido')
        candidate = self._inside_root(os.path.join(self.root, path.lstrip('/')))
        # O index também pode ser um symlink; validar novamente é indispensável.
        if os.path.isdir(candidate):
            candidate = self._inside_root(os.path.join(candidate, 'index.html'))
        if not os.path.isfile(candidate):
            raise NotFoundError('Arquivo não encontrado')
        return candidate
