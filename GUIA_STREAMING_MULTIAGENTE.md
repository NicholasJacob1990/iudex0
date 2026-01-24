Guia Tecnico: Interface de Streaming de Pensamento Multi-Agente em Tempo Real
=============================================================================

Visao Geral e Motivacao
-----------------------

Imagine aguardar 30 segundos olhando para uma tela em branco ou um icone de
carregamento enquanto uma IA processa sua solicitacao - e uma experiencia
frustrante para o usuario. De fato, "usuarios olhando para uma tela em branco
ou um spinner por meio minuto podem pensar que o sistema travou", o que gera
ansiedade e ma experiencia. A solucao e tornar essa espera interativa e
transparente, transmitindo atualizacoes em tempo real do que esta ocorrendo
"nos bastidores" enquanto o agente de IA pensa e produz uma resposta.

Neste projeto, temos tres agentes de IA (GPT-5, Claude e Gemini) que devem
responder em paralelo a cada consulta do usuario. A arquitetura proposta e
multicamadas para suportar um produto SaaS multiusuario, combinando um
front-end React moderno com um back-end Python assincrono. Em linhas gerais:

Frontend (Next.js 14+ / React 18): Interface do usuario com tres fluxos
simultaneos (um por agente) exibindo "pensando..." seguido de "escrevendo..."
em tempo real, tipo uma timeline interativa. Tecnologias como Zustand e React
Query gerenciam estado e comunicacao, enquanto componentes UI (Tailwind +
shadcn/ui) e um editor WYSIWYG (TipTap) permitem apresentar e talvez editar
as respostas.

Backend (FastAPI + LangChain): Uma API Python assincrona orquestra chamadas
aos modelos de linguagem e processamento de midia (Whisper para voz,
PyPDF/pytesseract para PDFs/imagens, etc.). Usa-se Celery (com Redis) para
tarefas intensivas, garantindo que o servidor web permanece responsivo. O
LangChain gerencia fluxos multiagente e integra ferramentas de NLP (spaCy,
NLTK).

Banco de Dados (PostgreSQL): Persiste dados de usuarios, sessoes de
conversa/documentos e respostas de cada agente, garantindo que cada resultado
e armazenado com identificacao do agente e associada a sessao ou documento
relevante.

Cache e Filas (Redis + Celery): Aceleram buscas recorrentes e gerenciam filas
de tarefas pesadas, respectivamente, possibilitando processamento assincrono
escalavel sem bloquear o atendimento de novos usuarios.

Por que Streaming em Tempo Real? Porque mesmo que o processamento demore o
mesmo tempo total, atualizacoes continuas melhoram muito a UX, dando ao usuario
feedback imediato e a sensacao de que o sistema esta ativo e "pensando". Nosso
objetivo e exibir os tres agentes "pensando" e respondendo simultaneamente, em
vez de um silencio prolongado. A seguir, discutimos as estrategias de streaming
ideais, como estruturar o front-end e back-end para suportar multiplos fluxos
sincronos, como armazenar sessoes e respostas no banco, como orquestrar os
agentes via LangChain e as melhores praticas de UX/performance para esse caso.

Estrategias de Streaming em Tempo Real (SSE vs WebSockets)
----------------------------------------------------------

Para push de dados em tempo real do servidor para o cliente, ha duas abordagens
principais a considerar: Server-Sent Events (SSE) e WebSockets. A tabela abaixo
resume as diferencas e aplicacoes de cada tecnologia:

Criterio                     | Server-Sent Events (SSE)                       | WebSockets
---------------------------- | ---------------------------------------------- | -------------------------
Comunicacao                  | Unidirecional (servidor -> cliente). Ideal      | Bidirecional (full-duplex)
                             | para streaming de updates.                      | cliente <-> servidor.
Protocolo                    | HTTP/1.1 ou HTTP/2 (texto/event-stream).         | Protocolo dedicado (ws://
                             | Usa conexao HTTP persistente padrao.            | ou wss://), exige handshake
                             |                                                | fora do HTTP convencional.
Suporte no Navegador         | Nativo via API EventSource (excelente           | Amplamente suportado via
                             | compatibilidade). Sem libs extras.              | WebSocket API JavaScript.
Reconexao Automatica         | Sim - o EventSource reconecta automaticamente   | Nao nativamente - requer
                             | em falhas, com backoff exponencial.             | logica cliente para reconectar.
Complexidade                 | Baixa - implementacao simples (stream HTTP      | Moderada - demanda gerenciar
                             | continuo). Menos sobrecarga de infra.           | estados do socket, heartbeats,
                             |                                                | escalonamento de servidores WS.
Firewall/Proxy               | Funciona via portas HTTP padrao (80/443),        | Pode ser bloqueado por alguns
                             | geralmente nao bloqueado (parece trafego        | proxies/firewalls legacy; requer
                             | HTTP normal).                                   | configuracao para passar trafego WS.
Casos de Uso                 | Atualizacoes server->client em tempo real sem   | Aplicacoes interativas com envio
                             | interacao do cliente: notificacoes, feeds,      | frequente do cliente: chats
                             | progresso, streaming de respostas de IA, etc.   | bidirecionais, colaboracoes em
                             |                                                | tempo real, jogos multiplayer, etc.

Para nossa aplicacao (stream de pensamento dos agentes), SSE e a escolha
ideal. Precisamos apenas de comunicacao do servidor para o cliente (o usuario
faz a pergunta via HTTP normal, depois so recebe os fluxos dos agentes). SSE
fornece exatamente isso de forma simples: mantem uma conexao HTTP aberta e
envia eventos do servidor conforme novos dados ficam prontos. Como observado
em um case real, "SSE e ideal quando so precisamos de via unica - mais simples
de implementar que WebSockets, funcionando sobre HTTP padrao e com suporte
nativo nos navegadores via EventSource". Isso mantem nosso stack leve sem
necessidade de infra especial para WebSocket.

Outra grande vantagem e escalabilidade e robustez do SSE. Como e
essencialmente streaming de texto via HTTP, SSE e leve em recursos e facil de
escalar em producao. Um unico processo FastAPI pode gerenciar muitas conexoes
SSE concorrentes usando async IO, contanto que esteja configurado adequadamente
(por exemplo, ajustar o timeout keep-alive do Uvicorn e numero de workers para
suportar conexoes longas). SSE nao requer balanceadores ou proxies especiais -
servidores padrao HTTP ja dao conta. Em suma, "por ser so uma resposta HTTP sob
o capu, ele escala bem: conexoes SSE sao leves e nao exigem infraestrutura
especial como WebSockets". A principal consideracao e manter muitas conexoes
abertas, mas servidores async como Uvicorn lidam com isso; basta ajustar os
workers e usar event loop eficiente (uvloop) para cargas altas.

Dica: Em cenarios com altissima escala de usuarios, considere enviar um header
Connection: keep-alive e desativar compressao (Content-Encoding: none) na
resposta SSE para evitar que proxies (como do Vercel, Cloudflare, etc.)
bufferizem ou quebrem o stream. O SSE ja envia dados texto incrementais, entao
nao deve ser cacheado ou comprimido.

E WebSockets? Poderiamos usar WebSockets se precisassemos de interatividade
bidirecional - por exemplo, se os agentes de IA fossem conversar em multiplas
trocas com o cliente, ou se quisessemos que o cliente pudesse interromper
ou resumir streams via comandos em tempo real. Nao e o caso tipico aqui
(o fluxo comeca apos a pergunta e vai ate terminar). WebSockets traria
complexidade extra sem ganho claro para nosso caso. Portanto, a nao ser que
planeje funcionalidades futuras que requeiram canal duplex (como edicao
colaborativa da resposta em tempo real, etc.), WebSocket seria "overkill". SSE
nos atende bem com menos overhead. Como pontua uma comparacao, SSE tende a ser
preferido para notificacoes, feeds, atualizacoes de status, enquanto WebSockets
ficam para chats ou apps altamente interativos.

Em resumo, usaremos SSE para entregar o streaming dos pensamentos e respostas
de cada agente ao cliente. Cada agente enviara dados conforme processa a
consulta, e o front-end exibira tudo em sincronia. A implementacao de SSE sera
detalhada adiante, mas em alto nivel: teremos um endpoint FastAPI que mantem a
conexao aberta e envia eventos rotulados para distinguir cada agente, e no
front-end o EventSource recebera esses eventos e direcionara o conteudo ao
componente correto (ex. painel do agente GPT-5, Claude ou Gemini).

Arquitetura do Frontend: Streaming Multiagente em Paralelo
----------------------------------------------------------

No front-end (Next.js + React), precisamos exibir tres fluxos simultaneos -
um para cada agente de IA - de forma sincronizada e amigavel ao usuario. A UI
pode ser imaginada como tres colunas ou paineis lado a lado (um por agente), ou
ainda uma timeline combinada de eventos de todos agentes. Aqui sugeriremos o
formato tres paineis paralelos, pois facilita comparar as respostas dos
agentes. Cada painel mostrara o nome do agente, um indicador de status
("pensando..." ou "respondendo...") e o texto da resposta aparecendo em tempo
real conforme os tokens chegam.

Estado e Gerenciamento de Streaming
-----------------------------------

Usaremos React 18 com as capacidades de renderizacao assincrona e atualizacao
concorrente, garantindo que multiplos componentes possam atualizar quase
simultaneamente sem travar a UI. Duas bibliotecas sao destacadas para
gerenciar nosso estado e dados:

Zustand: Armazena o estado global leve, como por exemplo o estado atual de
cada agente (pensando, escrevendo, texto parcial acumulado, tempo de
pensamento, etc.), e referencia a sessao/documento atual. O Zustand e rapido e
simples, permitindo que diversos componentes leiam/atualizem estados reativos
fora da arvore de renderizacao do React.

React Query (TanStack Query): Gerencia consultas assincronas a API (FastAPI).
Podemos usa-lo para operacoes como obter a lista de sessoes do usuario, enviar
uma nova pergunta, ou carregar um documento. No caso do streaming em si, o
React Query pode iniciar a acao (por exemplo, via um mutation que aciona o
endpoint SSE), mas a recepcao dos dados sera tratada pelo SSE nativo. Ou seja,
usaremos React Query para a parte request (comecar uma conversa, talvez
registrar no banco), mas o fluxo continuo de respostas vira por SSE.

Fluxo geral no front-end: quando o usuario submete uma pergunta ou abre uma
sessao:

1. Chamamos uma funcao (poderia ser via React Query mutation) para inicializar
   a sessao. Essa chamada pode retornar imediatamente um session_id e talvez
   alguns meta-dados (ex: quais agentes serao invocados).
2. Em seguida, abrimos uma conexao SSE para receber as respostas em streaming.
   Por exemplo, usamos new EventSource("/api/stream?session_id=123") apontando
   para nosso endpoint de stream do FastAPI. Essa conexao SSE permanecera
   aberta recebendo eventos do servidor.
3. No EventSource, definimos manipuladores para diferentes tipos de evento.
   Podemos configurar o backend para enviar eventos nomeados por agente.
   Exemplo: event: gpt5 com data: {...} contendo um chunk de texto, event:
   claude etc. No front, fazemos source.addEventListener("gpt5", handlerGpt5)
   etc., ou usamos o evento padrao message com um payload JSON indicando o
   agente.
4. A medida que chegam eventos, atualizamos o estado correspondente. Por
   exemplo, o handler do agente GPT-5 concatena o novo texto ao campo
   state.agents.gpt5.text no Zustand, e talvez atualiza status para
   "escrevendo".
5. O componente React que renderiza o painel do GPT-5 assina o estado via
   Zustand (ou recebe via props de um contexto) e re-renderiza incrementalmente
   mostrando o novo texto. O mesmo para os outros agentes.

Essa abordagem garante independencia: cada painel de agente atualiza apenas
quando seu proprio estado muda, evitando re-renderizar toda a pagina em cada
token recebido. Isso melhora performance (tres pequenas atualizacoes separadas
em vez de uma grande).

Exibindo "pensou por Xs" e "escrevendo..."
------------------------------------------

Uma exigencia de UX e mostrar quanto tempo o agente "pensou" antes de comecar
a responder, e entao indicar que esta "escrevendo" enquanto transmite a
resposta. Implementaremos isso assim:

Assim que o usuario envia a pergunta, imediatamente renderizamos nos tres
paineis algo como: "GPT-5 esta pensando... (tempo)", "Claude esta pensando...",
etc. Essa e a fase de pensamento inicial.

Medimos o tempo decorrido ate cada agente comecar a responder. Existem duas
maneiras:

No cliente: marcar o timestamp no envio da pergunta e, no primeiro evento de
resposta recebido para cada agente, calcular a diferenca. Por exemplo, se o
primeiro token do GPT-5 chegou em 4.2 segundos, exibimos "(pensou por 4.2s)"
antes do texto.

No servidor: o backend pode enviar um evento especial quando a resposta de um
agente comeca, incluindo o tempo. Ex: event: start_agent\ndata: {"agent":
"GPT-5", "think_time": 4.2}\n\n. Mas isso requer o servidor medir
internamente. E mais simples calcular no front mesmo, pois o tempo percebido
pelo usuario inclui latencia de rede de qualquer forma.

Quando o primeiro token chega, atualizamos o painel: substituimos "pensando..."
por "escrevendo resposta..." e talvez exibimos em cinza pequeno "(pensou por
4.2s)" ao lado do nome do agente. Em seguida, abaixo disso, o texto da
resposta comeca a aparecer em tempo real.

Cada token novo do agente e anexado ao texto mostrado. Podemos estilizar de
forma que o texto "digitado" pareca um teletipo (como em chats de IA comuns).
O TipTap (WYSIWYG) pode ser utilizado aqui para permitir formatacao rica ou
edicao posterior, mas atencao: atualizar um editor rico a cada token pode ser
custoso. Uma estrategia e acumular texto em um <pre> simples durante o
streaming e, ao final, inserir o texto completo no TipTap editor para
possiveis ajustes pelo usuario. Dessa forma, a performance durante o streaming
melhora.

Enquanto um agente esta respondendo, os outros podem ainda estar pensando ou
ja finalizando - todos operam em paralelo. Portanto, podemos ter cenarios em
que:

- GPT-5 comeca a responder em 3s e termina em 15s.
- Claude comeca em 5s, termina em 12s.
- Gemini comeca em 8s, termina em 10s.

A UI deve refletir isso: cada painel independentemente mostra seu progresso. O
usuario vera talvez primeiro o texto do GPT-5 surgir (ja que comecou cedo, mas
terminou por ultimo nesse exemplo), enquanto os outros aparecem depois ou
terminam antes. Nao ha problema - a interface e paralela de proposito.

Se quisermos uma visualizacao tipo timeline global, poderiamos tambem
apresentar uma linha do tempo mesclada: por exemplo, marcadores de quando cada
agente iniciou e terminou. Isso e opcional, mas enriquece a transparencia.
Poderia ser implementado exibindo, fora dos paineis, itens cronologicos:
"3.0s: GPT-5 comecou a responder", "5.0s: Claude comecou a responder", "10.1s:
Gemini respondeu completamente", etc. Contudo, para simplicidade, focamos na
apresentacao por painel, mencionando apenas o tempo de pensamento e deixando
implicito quando termina (quando o texto para de chegar e possivelmente um
icone de check aparece).

Atualizacao de Estado e Performance
-----------------------------------

Algumas boas praticas para manter o front-end fluido enquanto 3 fluxos de
texto chegam:

Batching e Renderizacao Parcial: O React 18 ja faz batching de varias
atualizacoes ocorridas no mesmo tick, mas se tokens chegam muito rapido,
podemos explicitamente agrupar atualizacoes. Por exemplo, usar
requestAnimationFrame ou um pequeno setTimeout de alguns milliseconds para
lotear multiplos tokens antes de desencadear um re-render. Assim, evitamos
re-render a cada caractere.

Uso de refs para texto: Em vez de guardar todo o texto em um estado React (que
causa render do componente a cada alteracao), podemos usar uma referencia a um
elemento DOM e simplesmente appendar texto no no de texto a medida que chega.
Essa tecnica (quando a formatacao e simples) pode reduzir dramaticamente
overhead de renderizacao. Apos finalizado, podemos sincronizar o conteudo final
no estado ou editor.

Evitar trabalho desnecessario: Desabilitar recursos pesados durante streaming,
exemplo: se for usar syntax highlight ou analise de sentimentos sobre a
resposta, so faca apos a resposta completa, nao dinamicamente enquanto digita.

Responsividade: Certificar que os tres paineis se ajustam bem mesmo em telas
menores, possivelmente ficando em stack vertical no mobile. O Tailwind CSS
facilita isso com utility classes responsivas.

Feedback de conclusao: Quando cada agente termina sua resposta, podemos trocar
o indicador "escrevendo..." por um icone de concluido ou uma palavra
"Concluido em 15s". Isso informa claramente que aquele fluxo terminou. Podemos
calcular o tempo total (pensamento+escrita) facilmente: timestamp fim -
timestamp inicio.

Por fim, o front-end deve lidar com erros ou timeouts graciosamente. Por
exemplo, se um dos agentes falhar (erro na API do modelo) ou demorar demais, o
backend pode enviar um evento de erro para aquele agente. O componente entao
mostraria "Erro: agente nao respondeu" ou "Tempo excedido" no painel
correspondente. Os outros agentes continuariam normalmente. Isso reforca a
vantagem de separar os fluxos - um agente travar nao impede os outros de
mostrarem resultado.

Arquitetura do Backend: FastAPI, SSE e Orquestracao com Celery/LangChain
------------------------------------------------------------------------

No back-end, combinamos FastAPI (framework web async) com Celery (fila de
tarefas distribuidas) e LangChain (orquestracao de LLMs) para atender as
requisicoes de forma escalavel. A arquitetura segue um padrao de decoupling: a
requisicao HTTP do usuario e rapidamente atendida iniciando processamento em
background e abrindo um canal de streaming de resultados. Isso evita bloquear
o servidor web em operacoes lentas e permite escalar cada parte conforme a
demanda.

Fluxo de Processamento Assincrono
---------------------------------

Recepcao da Pergunta: O usuario envia uma pergunta (ou comando, ou documento a
ser processado) via uma chamada HTTP (por ex, POST /api/query). O FastAPI
valida autenticacao, registra no banco uma nova sessao e imediatamente inicia
o processo dos agentes. Neste momento, ja retornamos algo ao cliente? Em vez
de retornar todos os resultados ja prontos (impossivel pois vai demorar),
retornamos uma resposta streaming SSE. Ou seja, o endpoint HTTP faz return
StreamingResponse(generator()) onde generator() e um gerador async que ira
produzir os eventos SSE gradualmente.

Disparando Tarefas para Agentes: Dentro desse gerador (ou antes dele),
orquestramos a chamada aos tres modelos de IA em paralelo. Ha duas estrategias
possiveis:

Async I/O no FastAPI: Como as chamadas as APIs do OpenAI/Anthropic/Google sao
principalmente bound por I/O (rede), podemos utiliza-las de forma assincrona
diretamente. Por exemplo, usando o pacote oficial OpenAI com stream=True para
obter um iterator de tokens, e chamadas HTTP async para Anthropic e Google.
Lancamos todas quase simultaneamente usando asyncio.create_task ou
asyncio.gather. A medida que cada coroutine traz dados, vamos colocando em uma
fila assincrona de eventos.

Tarefas Celery: Alternativamente, delegamos cada chamada de agente a um worker
Celery separado. O FastAPI enviaria 3 tarefas (uma para GPT-5, etc.) para filas
especificas, e entao nosso generator SSE ficaria monitorando o progresso dessas
tarefas (via polling do estado ou recebendo mensagens pub/sub no Redis). Cada
vez que um pedaco de resposta chega de uma tarefa, forwardamos via SSE para o
cliente.

Cada abordagem tem pros e contras. Chamar as APIs de forma async direto no
FastAPI simplifica (menos moving parts) e tem baixa latencia, mas consome
recursos do worker web (mesmo que async). Ja usar Celery adiciona robustez
(pode distribuir em varias maquinas, re-tentar em falha, etc.), porem complica
o streaming em tempo real (precisamos de polling ou pub/sub para obter os
tokens). Uma solucao mista e possivel: usar Celery para tarefas pesadas (ex:
pre-processamento como rodar Whisper em um audio, ou extrair texto de PDF), mas
para a parte de gerar texto dos LLMs (que sao chamadas de rede de curta
duracao), usar async in-process pode ser suficiente. Em ambos os casos, nenhum
passo bloqueante trava o loop principal - o modelo de concorrencia do Python
(asyncio ou processos Celery) garante que possamos atender outros usuarios
enquanto esses agentes trabalham em background.

Streaming de Eventos SSE: O core do endpoint FastAPI sera um generator
assincrono que coleta resultados dos agentes e os envia ao cliente. Em
pseudo-codigo:

    @app.get("/stream")
    async def stream_response(session_id: str):
        async def event_stream():
            # Inicia tarefas async para cada agente
            tasks = [generate_response(agent, session_id) for agent in AGENTS]
            # Marca tempos de inicio
            start_times = {agent: time.time() for agent in AGENTS}
            # Enquanto alguma tarefa nao concluida, obtenha resultados conforme prontos
            done = [False, False, False]
            while not all(done):
                for i, task in enumerate(tasks):
                    if not done[i] and task.done():  # se terminou ou falhou
                        done[i] = True
                        result = task.result()  # resultado final ou parcial restante
                        yield f"event: {AGENTS[i]}_end\\ndata: {result}\\n\\n"
                    elif not done[i]:
                        # Tentar pegar proximo token parcial dessa tarefa
                        token = await task.aget()  # ilustrativo; real code depende lib
                        if token:
                            # No primeiro token, enviar evento de inicio com tempo pensado:
                            if not "started" in session_state[AGENTS[i]]:
                                think_time = time.time() - start_times[AGENTS[i]]
                                yield (
                                    f"event: start\\ndata: {AGENTS[i]} pensou por "
                                    f"{think_time:.1f}s\\n\\n"
                                )
                                session_state[AGENTS[i]] = "started"
                            # Enviar token como evento
                            yield f"event: {AGENTS[i]}\\ndata: {token}\\n\\n"
                await asyncio.sleep(0)  # cede controle, permitindo outras coroutines rodarem

O acima e apenas conceitual. A ideia e que iteramos continuamente verificando
cada tarefa de agente:

- No primeiro token de cada agente, emitimos um evento indicando que aquele
  agente comecou a escrever (incluindo o tempo de pensamento calculado).
- Em cada token subsequente, emitimos eventos identificados pelo nome do
  agente com o texto.
- Quando a tarefa conclui, emitimos um evento final talvez com algum marcador
  de fim ou so paramos de enviar daquele.
- O loop termina quando todos agentes sinalizaram conclusao.

Essa logica pode variar conforme a biblioteca. Por exemplo, a API do OpenAI
com stream=True fornece um iterator onde cada item ja e um chunk de texto. O
Anthropic tambem oferece streaming. Precisaremos integrar cada um no loop
(talvez transformando em AsyncGenerators uniformes). Alternativamente, cada
tarefa Celery pode pushar tokens para Redis pub/sub channels
(session_123_agent_gpt5), e aqui assinamos esses canais - mas isso complica,
pois Python asyncio nao integra nativamente com Redis pubsub facilmente sem
bloquear. Poderiamos rodar um thread para ouvir Redis e postar em asyncio via
asyncio.Queue.

Em implementacoes do mundo real, muitas vezes usam-se callbacks ou handlers de
streaming das libs: ex. OpenAI Python lib permite passar uma funcao
on_token_chunk que seria chamada para cada pedaco. O LangChain abstrai isso
com Callback Managers: podemos definir um callback para eventos de novo token
do LLM. Assim, poderiamos implementar um CallbackHandler custom que, ao
receber um token de certo agente, faz algo como queue.put((agent_name, token)).
Nosso generator SSE entao simplesmente retira dessa fila e faz yield dos
eventos.

Envio e Encerramento: O StreamingResponse do FastAPI enviara ao cliente todos
os eventos gerados. Lembre-se de configurar media_type="text/event-stream" e
cabecalhos de SSE apropriados. Quando todos agentes terminarem, o generator
completa, o que fecha a conexao SSE do lado do servidor. O front-end
(EventSource) detectara fim de stream (pelo fechamento ou por receber um evento
especial de conclusao que podemos enviar, ex: event: done).

Em suma, essa arquitetura assegura que nenhum processamento pesado ocorre na
thread de requisicao - toda espera e assincrona ou delegada. Como descrito no
case da Senseloaf, "nenhum processamento pesado bloqueia o servidor FastAPI
principal; podemos escalar cada parte independentemente: se o gargalo for
CPU-bound, adicionamos workers Celery; se precisarmos suportar mais conexoes
clientes simultaneas, escalamos instancias FastAPI; o Redis no meio lida com a
troca de mensagens em alta velocidade". Ou seja, para um SaaS multiusuario,
basta aumentar horizontalmente os workers adequados para suportar mais usuarios
sem interferencias - isolamento por design.

Orquestracao Multiagente com LangChain
--------------------------------------

O LangChain entra para facilitar a integracao dos LLMs e ferramentas no fluxo.
Embora poderiamos chamar as APIs dos modelos diretamente, o LangChain traz
abstracoes uteis:

Interface unificada de LLMs: Podemos configurar wrappers para cada modelo
(ex: llm_gpt5 = OpenAI(model="gpt-5", streaming=True), llm_claude =
Anthropic(model="claude-v2", streaming=True), etc.) e usar metodos
padronizados. LangChain ja suporta chamadas assincronas para OpenAI e
Anthropic, permitindo rodar varias em paralelo. Por exemplo, ha await
llm_gpt5.agenerate([prompt]) que retorna de forma assincrona. Dessa forma,
podemos await asyncio.gather(llm_gpt5.agenerate(...), llm_claude.agenerate(...),
llm_gemini.agenerate(...)) para disparar todos simultaneamente.

Chains e Tools: Se nossas agentes precisam acessar documentos, podemos
construir Chains especificos para cada um. Ex: um RetrievalQAChain para GPT-5
usando embeddings especificos, outro para Claude, etc. Ou usar a classe de
Agente do LangChain se um agente for fazer varios passos. Entretanto, no nosso
caso os agentes nao interagem entre si; sao independentes. Entao podemos criar
tres chains ou prompts isolados.

Callbacks para streaming: Como mencionado, LangChain permite passar um
CallbackManager aos LLMs com handlers para eventos de token. Implementaremos um
handler que, a cada token gerado, identifica o agente e propaga o token para o
stream SSE. Isso encapsula a logica de fila de eventos. Por exemplo, um
pseudocodigo:

    from langchain.callbacks.base import BaseCallbackHandler

    class SSECallbackHandler(BaseCallbackHandler):
        def __init__(self, agent_name, send_queue):
            self.agent = agent_name
            self.queue = send_queue
        def on_llm_new_token(self, token: str, **kwargs):
            # Called for each new token from LLM
            self.queue.put_nowait((self.agent, token))

Depois instanciamos handler_gpt5 = SSECallbackHandler("GPT-5", queue) e passamos
para o LLM: llm_gpt5 = OpenAI(..., callbacks=[handler_gpt5]). Repetir para
outros agentes. Assim, quando chamarmos llm_gpt5.agenerate(), ele internamente
invoca o handler a cada token.

Controle de tempo e timeout: LangChain nao impoe limites de tempo por padrao,
mas podemos envolver chamadas em um asyncio.wait_for para garantir nenhum
agente demore demais. Ex: await asyncio.wait_for(llm_gemini.agenerate([prompt]),
timeout=30). Alem disso, podemos configurar nos parametros do modelo um limite
de tokens gerados, para evitar respostas excessivamente longas. Isso garante
que mesmo se um modelo "se perder" em uma resposta enorme, ele sera cortado em
um ponto razoavel.

Execucao paralela: Vale ressaltar que a execucao assincrona no Python com
asyncio e single-threaded, mas coopera em I/O. Como as chamadas aos modelos
externos sao I/O-bound (aguardam resposta da API), isso funciona bem - ja foi
demonstrado que fazer multiplas chamadas de LLM concurrently pode acelerar
significativamente em comparacao a sequencial. Para processamento CPU-bound
(como rodar spaCy num texto grande), usariamos o Celery (processo separado).

Na pratica, orquestrar com LangChain pode se traduzir em um codigo como:

    async def generate_responses(prompt, session):
        # Preparar doc (se houver) para contexto: ex obter texto de PDF ou transcricao
        prompt_full = f"{prompt}\\nConteudo referente: {context}"
        results = {}
        llm_openai = ChatOpenAI(model="gpt-5", streaming=True,
                                callbacks=[SSECallbackHandler("GPT-5", queue)])
        llm_claude = Anthropic(model="claude-2", streaming=True,
                               callbacks=[SSECallbackHandler("Claude", queue)])
        llm_gem = GooglePalm(model="gemini", streaming=True,
                             callbacks=[SSECallbackHandler("Gemini", queue)])
        await asyncio.gather(
            llm_openai.apredict(prompt_full),
            llm_claude.apredict(prompt_full),
            llm_gem.apredict(prompt_full),
        )
        return results

(Nota: Codigo ilustrativo; .then() nao e real em Python async, usar pattern
normal de await/gather.)

O importante e: LangChain simplifica a orquestracao paralela e integracao de
ferramentas. Tambem facilita manter memoria de sessao se quisermos dar contexto
de conversas anteriores aos agentes. Por exemplo, podemos armazenar o historico
de chat na sessao e pre-prontar: "User perguntou X. Assistant respondeu Y. Agora
user pergunta Z." para cada modelo, se quisermos que eles tenham memoria. O
LangChain tem utilitarios de ConversationBufferMemory etc., mas podemos
gerenciar manualmente tambem via nosso banco.

Persistencia de Sessoes e Respostas no PostgreSQL
-------------------------------------------------

Para um sistema SaaS multiusuario, e fundamental salvar cada interacao no
banco de dados tanto para contexto (memoria de conversa) quanto para auditoria,
analytics, ou recuperacao posterior. Vamos adotar um modelo relacional simples,
seguindo o padrao Usuarios -> Sessoes -> Mensagens:

Tabela de usuarios: armazena informacoes do usuario (id, nome, email, etc.).

Tabela de sessoes: representa uma conversa ou analise de documento. Campos
tipicos: session_id (PK), user_id (FK para usuarios), tipo (ex: "chat" ou
"document"), referencia ao documento se houver, data de inicio, data de fim,
etc. Cada nova pergunta do usuario pode criar uma sessao ou reutilizar uma
existente (no caso de chat continuo).

Tabela de mensagens: armazena cada mensagem ou resposta dentro de uma sessao.
Campos: message_id (PK), session_id (FK), sender (quem enviou: pode ser "user"
ou o nome do agente "GPT-5", "Claude", etc.), text (conteudo da mensagem),
timestamp. Essa estrutura captura tanto a pergunta do usuario quanto as
respostas multiplas dos agentes.

No caso particular em questao, se cada pergunta origina exatamente tres
respostas (uma de cada agente), podemos modelar que cada sessao tem 1 mensagem
do usuario e 3 mensagens (respostas) dos assistentes. Isso se encaixa bem no
modelo acima. Um exemplo de esquema dessas tabelas em SQL (simplificado) seria:

    CREATE TABLE sessions (
        session_id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(user_id),
        start_time TIMESTAMPTZ DEFAULT NOW(),
        end_time TIMESTAMPTZ
    );

    CREATE TABLE messages (
        message_id SERIAL PRIMARY KEY,
        session_id INTEGER REFERENCES sessions(session_id),
        sender VARCHAR(50) NOT NULL,
        message_text TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

Como referencia, um guia de design de historico de chat com Postgres recomenda
exatamente essa estrutura de tabela de sessoes e tabela de mensagens, vinculadas
por chaves estrangeiras. Essa normalizacao permite extrair facilmente todas
mensagens de uma sessao (para reconstruir a conversa) e aplicar filtros por
usuario, data, etc. No nosso caso multiagente, o campo sender diferencia qual
agente respondeu. Alternativamente, poderiamos ter uma tabela separada de
"respostas de agentes" com colunas especificas para cada agente - mas isso nao
e escalavel (se futuramente tivermos 4o agente?) e foge do modelo de chat
tradicional. Usar a tabela de mensagens unificada e mais flexivel.

Persistindo dados durante a conversa: Assim que o usuario envia uma pergunta e
criamos a sessao, inserimos a mensagem do usuario. Conforme cada agente
finaliza sua resposta (ou ate parcialmente durante streaming, se quisermos
salvar versoes incrementais, embora nao seja tao comum), inserimos uma linha na
tabela de mensagens com o conteudo final daquele agente. Provavelmente faz
sentido esperar ate o agente terminar para salvar a resposta completa de uma
vez - assim armazenamos apenas a saida final. O streaming em si pode nao
precisar persistir cada token (seria excesso de I/O no banco). Podemos
acumular no codigo e salvar quando completo.

Relacionamento de documentos: Se cada sessao esta associada a um documento
(ex: o usuario faz perguntas sobre um PDF), poderiamos ter uma tabela de
documentos e um campo document_id na sessao. Assim, sabemos que aquela sessao
envolvia certo documento, e possivelmente podemos armazenar tambem no banco
embeddings ou sumarios desse documento para reutilizar. Mas isso e alem do
escopo principal aqui.

Consulta e recuperacao: Com as tabelas montadas, podemos construir API
endpoints para:

- Listar sessoes do usuario (mostrando talvez ultimos resultados de cada agente
  ou status se incompleta).
- Recuperar detalhes de uma sessao (incluindo todas mensagens) para exibir
  historico ou permitir retomar a conversa.
- Apagar sessoes (importante se armazenamos dados possivelmente sensiveis dos
  usuarios).

Adicionalmente, esse modelo facilita calcular metricas: e.g., quantas vezes
GPT-5 concorda com Claude, tempos medios de resposta de cada modelo, etc., ja
que temos cada resposta separada.

Exemplo pratico: digamos que o usuario Alice (user_id 42) fez uma pergunta
sobre um documento Doc123. Criamos session_id=100 com user_id=42,
document_id=123. Inserimos messages:

- id 1: session 100, sender "user", text "Pergunta sobre o doc ...?",
  timestamp t0.
- id 2: session 100, sender "GPT-5", text "Resposta do GPT5 ...", timestamp t1.
- id 3: session 100, sender "Claude", text "Resposta do Claude ...", timestamp t1.
- id 4: session 100, sender "Gemini", text "Resposta do Gemini ...", timestamp t2.

Agora, se Alice voltar amanha e continuar conversando na mesma sessao (se
suportarmos isso), novas mensagens vao sendo anexadas com o mesmo session_id
100 (pergunta follow-up do usuario, e novas respostas dos agentes). Ou, se
tratamos cada pergunta isoladamente, encerramos a sessao marcando end_time apos
a primeira interacao.

Dica de implementacao: usar um ORM como SQLAlchemy (assincrono) ou Tortoise ORM
pode agilizar o desenvolvimento. Crie modelos para User, Session, Message e
utilize relacoes. O SQLAlchemy async funciona bem com FastAPI. Lembre de
configurar pool de conexoes adequado e possivelmente usar SQLAlchemy Core +
AsyncSession para melhor controle em alta concorrencia. Como estaremos fazendo
muitas insercoes pequenas (mensagens), agrupar em transacoes por sessao
(inserir 3 respostas em batch) pode ser eficiente.

Para manter desempenho do banco a longo prazo, considere indices: por exemplo,
um indice em (session_id, sender) se frequentemente filtraremos mensagens de um
agente especifico em uma sessao (pouco provavel). Mais util talvez: indice por
user_id em sessions para listar sessoes de um usuario rapidamente.

Boas Praticas de UX e Performance
---------------------------------

Implementar uma interface de "streaming de pensamento" multiagente traz
desafios de UX unicos. Concluimos com algumas melhores praticas para garantir
que a experiencia seja fluida, informativa e escalavel:

Mantenha o usuario informado constantemente: Nunca deixe o usuario no escuro
durante processamento. Mostre imediatamente indicadores de pensando... para
cada agente. Atualize para escrevendo... assim que comecarem a responder,
incluindo o tempo decorrido. Essa transparencia reduz a ansiedade e aumenta a
confianca no sistema.

Distinga claramente cada agente: Utilize rotulos ou estilos diferentes para
as respostas de cada IA. Por exemplo, caixas de cor ou avatar do modelo (ex:
icone do OpenAI, logo do Anthropic) no cabecalho de cada painel. Assim o
usuario identifica facilmente "quem" disse o que. Isso e crucial ao comparar
respostas.

Organizacao visual: Em desktops, coloque os tres paineis lado a lado para
facil comparacao horizontal. Em dispositivos moveis, talvez uma abaixo da outra
com o nome do agente fixo no topo de cada secao. Use componentes de layout
responsivo do shadcn/ui (que aproveita Radix UI + Tailwind) para construir
layout de cards ou tabs representando cada agente. Por exemplo, tres Card
compondo uma grade de 3 colunas.

Timeline e timestamps: Considere mostrar timestamps relativos ou absolutos de
eventos, se for util. Por exemplo, "(pensou por 3.8s, resposta finalizada em
12.4s)". Isso oferece ao usuario entendimento de qual modelo foi mais rapido e
quanto tempo levou. Pode ser apresentado em tooltip ou texto pequeno abaixo da
resposta.

Desempenho no front: Como citado, minimizar reflows e re-renders
desnecessarios. Tambem, o Next.js App Router permite usar streaming de servidor
(Server Components streaming) - porem, neste caso especifico, a maior parte e
client-side devido a SSE. Ainda assim, manter o bundle leve ajuda: carregar
TipTap de forma dinamica (lazy) somente quando o usuario realmente for editar
um texto, por exemplo. Nao carregar bibliotecas pesadas de NLP no front (deixe
isso para o backend).

Manuseio de erros: Prepare a interface para falhas de cada agente
individualmente. Exiba mensagens de erro amigaveis, como "Claude apresentou um
erro ao processar." e de opcao de retry apenas daquele agente, talvez. Gracas
a arquitetura paralela, um agente falhar nao impede os outros de retornarem
algo - explique isso ao usuario, para que ele entenda que pode confiar nos
outros resultados.

Persistencia e sincronia: Lembre-se de que estamos salvando as respostas no
banco. Assim, voce pode oferecer ao usuario a capacidade de visualizar sessoes
passadas, ou recarregar a pagina e ainda ver as respostas que ja foram obtidas.
Implementar uma pagina de historico de sessoes usando React Query para fetch do
backend e uma boa pratica. Nesse caso, voce pode armazenar no estado global se
uma sessao atual esta em andamento, e sincronizar com SSE eventos.

Escalabilidade horizontal: Em producao SaaS, havera multiplos instancias do
backend e possivelmente multiplos servidores web. SSE pode exigir sticky
sessions ou um mecanismo de pub/sub central (como Redis) para permitir que
qualquer instancia envie eventos. Nossa arquitetura ja usa Redis, entao e
possivel evoluir para um modelo em que, ao iniciar uma sessao, fixamos qual
instancia atendera SSE daquela sessao (ou usamos um servidor de eventos
dedicado). De qualquer forma, monitore recursos: SSE consome uma conexao por
cliente - com muitos usuarios, ajuste limites de file descriptors, threads
Celery, etc.

Controle de concorrencia por usuario: Como cada consulta envolve 3 chamadas de
API externas, voce pode implementar limites de taxa (rate limiting) para evitar
abuso. Por exemplo, maximo de X solicitacoes simultaneas por usuario ou um
atraso minimo. Isso previne sobrecarregar seu sistema e gastos inesperados nas
APIs de terceiros.

UX: pos-processamento: Apos todas respostas chegarem, pense em recursos
adicionais: talvez um botao "Comparar respostas" que destaque diferencas entre
as tres (pode usar diffs ou LLMs para cruzar). Ou um botao "Unir melhores
partes" (futuro interessante: usar um LLM para combinar as tres respostas em
uma sintese). Essas funcionalidades nao fazem parte do core pergunte->responda,
mas podem diferenciar seu produto.

Feedback loop: De opcao para o usuario avaliar qual resposta foi melhor ou se
foram uteis. Isso pode ser armazenado para possivelmente treinar modelos
futuros ou simplesmente para analise de qualidade.

Seguranca e PII: Sendo um SaaS, cuide dos dados sensiveis. Transmita via HTTPS
sempre (SSE e compativel com SSL). Autentique as requisicoes SSE (FastAPI pode
exigir token ou cookie valido; o EventSource enviara cookies se same-site). No
lado do cliente, evite logar conteudos sensiveis no console.

Em resumo, focamos em tornar a experiencia do usuario suave e confiante: ele
ve que cada agente esta engajado na tarefa ("pensando" com um spinner
possivelmente), entao ve as respostas surgindo. A aplicacao parece responsiva
mesmo durante operacoes longas, porque sempre ha algo acontecendo na tela. Essa
abordagem ja foi validada por estudos de UX: "push de atualizacoes em tempo
real faz a experiencia parecer mais rapida e interativa, evitando necessidade
de polling ou espera passiva".

Conclusao
---------

Implementar um streaming de pensamento multiagente requer combinar tecnicas de
desenvolvimento web em tempo real, concorrencia assincrona e UX de conversacao.
Recapitulando os pontos-chave da nossa solucao:

- Utilizamos Server-Sent Events para streaming one-way simplificado, ideal para
  enviar respostas de IA em tempo real sem overhead de WebSockets. Isso nos
  permite atualizar a UI token por token quase instantaneamente.
- Arquitetamos front-end e back-end de forma desacoplada e escalavel: FastAPI
  enfileira trabalho pesado nos workers Celery e imediatamente comeca a mandar
  eventos SSE para o cliente. Assim, mesmo com muitos usuarios, podemos
  escalar horizontalmente sem gargalos - mais instancias FastAPI para suportar
  conexoes, mais workers Celery para throughput de processamento.
- Armazenamos todos os dados relevantes no PostgreSQL de forma normalizada
  (usuarios, sessoes, mensagens), garantindo persistencia das conversas e
  permitindo contexto em multi-turn. O esquema sugerido com tabela de mensagens
  ligadas a sessoes facilita consultas e manutencao do historico.
- Orquestramos os 3 agentes de IA em paralelo usando recursos async do
  LangChain, que suporta chamadas concorrentes a LLMs como OpenAI e Anthropic.
  Empregamos callbacks de streaming para integrar com SSE e medimos tempos de
  latencia ("pensamento") de cada modelo. Tambem aplicamos timeouts e limites
  para seguranca e performance.
- Adotamos diversas otimizacoes de UX e performance: feedback constante ao
  usuario (pensando/escrevendo), UI paralela clara para cada agente,
  atualizacao de estado eficiente sem reflows excessivos, tratamento de erros
  isolado por agente, e consideracoes de escalabilidade para um ambiente SaaS
  multiusuario.

Em termos de ferramentas, recapitulando as recomendacoes para cada parte da
solucao:

Frontend: Next.js 14+ com App Router para poder usar API Routes ou Route
Handlers SSE facilmente; React 18 concurrent mode; Zustand para estado global
(por ex., status de agentes); React Query para acoes REST iniciais; Tailwind +
shadcn/ui para construir layout responsivo dos paineis; TipTap editor para
permitir edicao/formatacao das respostas (montado de forma otimizada apos
resposta completa).

Comunicacao em Tempo Real: API EventSource do navegador para consumir SSE; do
lado do FastAPI, StreamingResponse gerando text/event-stream. (Bibliotecas
auxiliares: poderia usar sse-starlette ou FastAPI-SSE para facilitar headers,
mas nao e estritamente necessario, o codigo manual nao e complexo).

Backend: FastAPI (async) para endpoints; SQLAlchemy async + Alembic para ORM e
migracoes; Redis para broker/result do Celery e possivelmente pub/sub de
eventos; Celery para tarefas intensivas (Whisper, OCR, etc.) configurado com
filas separadas priorizadas; LangChain para abstrair LLMs, memoria e callbacks;
asyncio/anyio para gerenciar concorrencia nas chamadas de modelo.

Outras: Whisper (OpenAI) para transcricao de audio integrado possivelmente via
uma tarefa Celery antes da geracao de respostas; pytesseract/pyPDF para ler
arquivos enviados, tambem via tarefas; spaCy/NLTK se precisarmos fazer
pos-processamento de linguagem nas respostas (por exemplo, extrair keywords das
respostas - isso poderia ate ser uma "ferramenta" do LangChain agent, embora no
nosso design cada agente e somente LLM, sem ferramentas explicitas).

Ao seguir esse guia, voce construira uma interface em que tres potentes
modelos de linguagem trabalham em unissono diante do usuario, cada um com seu
"fluxo de consciencia" visivel. Essa transparencia nao apenas melhora a UX,
mas tambem permite ao usuario compreender as diferencas de cada modelo e
confiar que o sistema esta efetivamente trabalhando na sua solicitacao em
tempo real. A arquitetura proposta e moderna, escalavel e alinhada as melhores
praticas para aplicacoes alimentadas por IA generativa em 2025. Boa codificacao
e bom streaming!

Referencias Utilizadas
----------------------

- Kumar, A. Streaming AI Agents Responses with SSE: A Technical Case Study
  (Senseloaf.ai, 2025) - descreve arquitetura FastAPI + Celery + SSE e
  vantagens do streaming em UX.
- Stringer, L. Building Stateful Conversations with Postgres and LLMs (2024)
  - discute modelo de persistencia de historico de chat com tabelas de sessions
  e messages.
- LangChain Documentation - secao de chamadas assincronas de LLMs, exemplificando
  chamadas concorrentes com OpenAI/Anthropic.
- Pedro Alonso, Real-Time Notifications with SSE in Next.js (2025) -
  comparacao SSE vs WebSocket e casos de uso (conteudo em ingles).
