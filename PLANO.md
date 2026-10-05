# Plano de implementação — Trabalho 1

**Objetivo:** entregar o projeto descrito no anexo, dentro de `t1`.
**Especificação:** enunciado anexado em 29/09/2026 e revisado em 05/10/2026.
**Arquitetura:** `HttpServer` aceita TCP e cria uma thread daemon por conexão;
`ConnectionHandler` mantém o ciclo HTTP; `RequestReader` delimita mensagens;
`RequestHandler`, `FileResolver` e `HttpResponse` resolvem e enviam arquivos.
**Revisão técnica (05/10/2026):** manter a pasta tests e usar nomes Python descritivos.

**Tecnologia:** Python 3.9+, exclusivamente biblioteca padrão, sockets bloqueantes.

## Decisões

- Implementação diretamente na pasta solicitada; t1 passou a ter repositório Git após a implementação inicial.
- Bind padrão `0.0.0.0`; porta CLI entre 1025 e 65535.
- Cabeçalhos até 16 KiB, corpo recebido até 1 MiB; framing ambíguo fecha com 400.
- Corpos com Content-Length são consumidos antes de processar a próxima mensagem.
- Transfer-Encoding não implementado: 400 e fechamento. Expect não implementado: 417 e fechamento.
- Arquivos enviados em blocos de 64 KiB, raiz administrada pelo grupo e estável durante execução.
- Date pode variar entre requisições feitas em segundos diferentes; os demais headers GET/HEAD devem coincidir.
- Captura BPF usa `tcp port 8080`; exibição Wireshark usa `tcp.port == 8080`.
- Medições reais e identificação dos integrantes permanecem para preenchimento.

## Etapas verificáveis

- [x] Criar clientes e testes: conformidade, corpos, timeout, bytes fragmentados, pipeline e concorrência; executar antes do servidor e registrar falha por ausência da implementação.
- [x] Implementar seis módulos e fixtures; executar suíte integrada em TCP real com bind 0.0.0.0.
- [x] Criar benchmark C1/C2; executar os dois modos com 10 requisições e verificar quantidade de conexões e bytes iguais.
- [x] Escrever README, modelo de relatório e documentação de todas as funções/métodos; conferir inventário por AST.
- [x] Revisar segurança, lifecycle e documentação; executar suíte completa e CLI antes de entregar.

## Foco da revisão

1. Symlink de diretório e de index.html escapando da raiz; prefixo www-secret.
2. Content-Length repetido, inválido e combinado com Transfer-Encoding.
3. HEAD em erros e em pipeline sem contaminar a resposta seguinte.
4. Timeout após bytes parciais, fechamento pelo cliente e desligamento com threads ativas.
5. Arquivo binário grande, tamanho por fstat e nenhuma listagem de diretório.

## Registro

- Enunciado lido e arquitetura preservada; nenhuma dependência externa.

- Suíte inicial: 23 testes passaram com sockets TCP reais locais; C1 abriu 10 conexões e C2 abriu 1. Medição local não é evidência do laboratório.

- Revisão independente: encontrado HEAD com cabeçalho excessivo enviando corpo; teste regressivo falhou antes da correção e passou depois.
- Verificação final: 24 testes sem falhas/erros; 72 funções/métodos presentes na documentação; identificadores verificados por AST.
- Servidor iniciado pela CLI, scripts HTTP/stream/concorrência e benchmarks C1/C2 executados com exit code 0; Ctrl+C encerrou sem traceback.
- Porta baixa, timeout NaN e bind loopback rejeitados conforme esperado.
- Nenhuma captura, RTT ou medição entre máquinas foi fabricada; conferir COMPARACAO_ENUNCIADO.md para pendências do laboratório.

## Correção da nomenclatura — 05/10/2026

- Renomeados métodos, parâmetros, atributos, imports e referências, preservando a lógica HTTP.
- Construtores e context managers agora usam os métodos especiais diretamente.
- Testes usam nomes test_... reconhecidos pelo unittest padrão, sem alterar o loader global.
- Comparação do enunciado corrigida e documentação/guia de estudo atualizados, inclusive inventário.
- Manter evidências reais separadas de validação local.

- Verificação após a correção: 24 testes integrados passaram; scripts CLI de conformidade, fluxo, concorrência e C1/C2 terminaram com código zero. Argumentos inválidos foram rejeitados e Ctrl+C encerrou sem traceback.
- Inventário conferido por módulo: 72 definições e assinaturas correspondem à documentação e ao guia; links de linha e índice atualizados.
