# Trabalho 1 — HTTP/1.1 sobre TCP

**Integrantes (até 3):** ___ / ___ / ___  
**Turma/data:** ___  **Grupo no Moodle:** ___  
**Servidor/IP/SO/Python:** ___  **Clientes/IPs/SO:** ___  
**Porta/raiz/timeout/Server:** ___  **Interface de captura:** ___

Preencha com evidências reais, remova orientações entre colchetes e exporte um único
PDF sucinto cobrindo as duas partes. Não copie os tempos de validação local.

## 1. Arquitetura e concorrência

`HttpServer` aceita TCP e cria uma thread daemon por conexão. `ConnectionHandler`
executa o ciclo persistente; `RequestReader` delimita mensagens; `RequestHandler`
seleciona resposta; `FileResolver` protege a raiz; `HttpResponse` gera headers e blocos.
Usamos threads pela simplicidade de I/O bloqueante e escala do laboratório. Uma thread
esperando um cliente não bloqueia as demais. Alternativas: pool com limite de threads,
select/epoll ou async. Limitação: sem limite de threads, muitos clientes podem consumir recursos.

**Diagrama e observações específicas do grupo:** ___

## 2. Conformidade

Substitua IP pelos endereços reais; guarde status e headers observados.

| Código/método | Comando (curl.exe no PowerShell) | Resposta obtida/evidência |
|---|---|---|
| 200 GET | `curl -i http://IP:8080/test.txt` | ___ |
| 200 HEAD | `curl -I http://IP:8080/test.txt` | ___ |
| 400 | `curl --http1.1 -i -H "Host:" http://IP:8080/` | ___ |
| 403 | `curl --path-as-is -i http://IP:8080/../../secret.txt` | ___ |
| 404 | `curl -i http://IP:8080/inexistente` | ___ |
| 405 | `curl -i -X POST http://IP:8080/test.txt` | ___ |

**Content-Length, Content-Type, Date, Server e ausência de corpo HEAD conferidos:** ___

## 3. Segurança: três tentativas distintas

| Request-target enviado (usar --path-as-is) | Request line completa | Resposta e referência |
|---|---|---|
| `/../../Windows/System32/drivers/etc/hosts` | ___ | ___ |
| `/%2e%2e/%2e%2e/secret.txt` | ___ | ___ |
| `/assets/../../../secret.txt` | ___ | ___ |

**Por que são rejeitadas:** percent-decoding precede validação; NUL, barra invertida e
dois-pontos são rejeitados; realpath resolve symlinks; commonpath compara componentes
com a raiz. O index.html também passa pela verificação. **Evidência do grupo:** ___

## 4. Transação completa de outra máquina

**Arquivo/stream/IPs:** ___  **Figura anotada:** ___

| Fase | Trama(s) | Flags/seq/ack e explicação |
|---|---|---|
| SYN | ___ | ___ |
| SYN/ACK | ___ | ___ |
| ACK | ___ | ___ |
| GET | ___ | ___ |
| Headers/corpo da resposta | ___ | ___ |
| FIN e ACKs de encerramento | ___ | ___ |

## 5. Atendimento simultâneo

**IPs das duas máquinas clientes:** ___ e ___  
**Comandos e horários sobrepostos:** ___  
**Log/captura e tramas que comprovam sobreposição:** ___  
**Resultado do cliente lento mais clientes paralelos:** ___

## 6. RTT

**Comando:** `ping -n 20 IP` (Windows) / `ping -c 20 IP` (Linux/macOS).  
**Mínimo/médio/máximo/perda:** ___ / ___ / ___ ms / ___ %.  
**RTT em segundos usado nas fórmulas:** ___ (dividir milissegundos por 1000).

## 7. C1 versus C2

**Recurso/tamanho/N:** `/test.txt` / ___ bytes / 10.  
**Repetições, ordem e estatística:** ___. **Critério de bytes:** soma de frame.len das tramas selecionadas.  
**Capturas:** ___ e ___. **Critério de tempo:** primeira–última trama do experimento.

| Cenário | Handshakes completos | Pacotes | Bytes de rede | Tempo de captura (s) | Tempo cliente (s) |
|---|---:|---:|---:|---:|---:|
| C1: conexão por pedido | ___ | ___ | ___ | ___ | ___ |
| C2: uma conexão | ___ | ___ | ___ | ___ | ___ |

**Economia de pacotes:** `100 × (P1 − P2) / P1` = ___ %.  
**Economia de bytes:** `100 × (B1 − B2) / B1` = ___ %.  
**Conferência de SYN/SYN-ACK/ACK e exclusão de retransmissões na contagem de handshakes:** ___

## 8. Overhead de abrir e fechar no C1

Selecione por stream os pacotes de handshake e encerramento sem payload HTTP. ACKs de
dados não são automaticamente overhead de conexão. Indique casos de ACK/FIN junto de dados.

| Fase | Tramas/critério | Pacotes somente controle | Soma frame.len (bytes) |
|---|---|---:|---:|
| SYN + SYN/ACK + ACK de abertura | ___ | ___ | ___ |
| FIN e respectivos ACKs | ___ | ___ | ___ |
| Total, sem duplicação | ___ | ___ | ___ |

**Pacotes de dados com controle agregado e tratamento adotado:** ___  
**Participação no total C1:** `100 × bytes_controle / B1` = ___ %.

## 9. Relação com RTT

Para objetos pequenos e pedidos sequenciais, desprezando transmissão e processamento:
`T_C1 ≈ 2·N·RTT`, `T_C2 ≈ (N+1)·RTT`, diferença ≈ `(N−1)·RTT`.
Cada conexão nova acrescenta um RTT de handshake; ambos os cenários têm N ciclos de
pedido/resposta. Com N=10, C1 gasta nove RTTs extras em handshakes.

**Previsão com RTT medido:** T_C1 = ___ s, T_C2 = ___ s, diferença = ___ s.  
**Diferença observada:** ___ s. **Diferença/RTT:** ___ RTTs.  
**Discussão de desvios (transmissão, fechamento, ACK atrasado, Nagle, perdas, escalonamento):** ___

## 10. Conclusão e interoperabilidade

**O que os resultados permitem concluir:** ___.  
**Por que RTT maior e mais pedidos por conexão ampliam o ganho:** ___.  
**Grupo parceiro/IPs/data:** ___.  
**A acessa B e B acessa A; HTML, CSS e imagem carregados:** ___.  
**Limitações e pendências:** ___.

Referências: RFC 9110; RFC 9112; Kurose & Ross, seção 2.2; documentação do código entregue.
