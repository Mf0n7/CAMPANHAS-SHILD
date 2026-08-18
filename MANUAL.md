# Manual — Campanhas SHILD

Guia de consulta. O [README.md](README.md) é o resumo; aqui está o detalhe de cada campo,
cada coluna da planilha e as armadilhas que dão dor de cabeça.

---

## 1. Rodar o sistema

```powershell
cd "C:\Users\Matheus Fontenele\Documents\projetos\SHILD\shild-system\RSPV capaign"
.\venv\Scripts\python.exe run.py
```

Abre em <http://127.0.0.1:8010>. Para parar: `Ctrl+C` na janela do terminal.

Tudo o que você digita, o poster e a lista de funcionários ficam no **banco** — localmente
um SQLite em `saidas/campanhas.db`, em produção o Postgres. Pode fechar e abrir sem perder
nada, e no servidor um redeploy não apaga a campanha.

---

## 2. A planilha de funcionários

Aceita `.csv` e `.xlsx`. Sua planilha de controle serve direto, sem editar.

O sistema **acha o cabeçalho sozinho** — não precisa estar na primeira linha. Se quiser
forçar, preencha o campo "linha do cabeçalho" ao importar.

O que a importação faz:

- pessoa nova → entra na base
- pessoa que já existia → atualiza (se o telefone mudou, a validação de WhatsApp é refeita)
- pessoa que saiu do arquivo → fica inativa, sai dos disparos, mas o histórico é preservado

Marcando **"Substituir a base atual"**, tudo é apagado antes — inclusive o histórico de envios.

A **ordem das colunas não importa** — o sistema lê pelo cabeçalho.

### Reimportar é seguro

A identidade de cada pessoa é **empresa + email/telefone**, não a posição no arquivo.
Corrigir a planilha, reordenar linhas ou inserir gente no meio não embaralha quem já recebeu.

| Coluna    | Obrigatória | O que faz                                                                                 |
|-----------|-------------|-------------------------------------------------------------------------------------------|
| `empresa`  | **sim**     | Vira o `{empresa}`: cabeçalho, saudação, assunto, rodapé, remetente e a imagem do WhatsApp. |
| `email`    | um dos dois | Para onde o email vai.                                                                      |
| `telefone` | um dos dois | Para onde o WhatsApp vai. Normalizado sozinho.                                               |
| `logo`     | não         | Link público do PNG da logo daquela empresa.                                                 |
| `nome`     | não         | Alimenta `{nome}` e `{primeiro_nome}` na saudação.                                           |

Linha sem **email nem telefone** é descartada e reportada na tela com o motivo.

### Nomes de cabeçalho aceitos

Não precisa escrever exatamente `email`/`empresa`/`logo`. Acento e maiúscula são ignorados:

- **email** — `email`, `e-mail`, `mail`, `endereço de email`
- **empresa** — `empresa`, `nome da empresa`, `razão social`, `cliente`, `organização`, `unidade`, `company`
- **logo** — `logo`, `link da logo`, `link da logo da empresa`, `url da logo`, `logo da empresa`, `imagem`, `link`
- **nome** — `nome`, `nome do funcionário`, `funcionário`, `colaborador`, `nome completo`
- **telefone** — `telefone`, `celular`, `whatsapp`, `fone`, `contato`, `número`

CSV com `;` ou `,` funciona igual — o separador é detectado sozinho, e acento no cabeçalho
não atrapalha.

### Escolher quais empresas recebem

Depois de importar, o **passo 4** lista as empresas com caixa de seleção. Só as marcadas
recebem — desmarcada fica na base, mas fora do disparo.

A seleção do **email é independente da do WhatsApp**: dá para mandar email para todas e
WhatsApp só para algumas. O contador ao lado dos botões mostra quantos destinatários a
seleção atual alcança, e o KPI "vão receber" reflete isso.

Marcar todas equivale a não filtrar nada.

### Corrigir um dado pelo sistema

Na tabela de destinatários, os campos em **azul** são editáveis: clique, digite, Enter.
`Esc` cancela. Editáveis: `empresa`, `logo`, `nome`, `email`, `telefone`.

A correção vale **na base**, até a próxima importação daquela pessoa. Serve para consertar
um telefone na hora do disparo; para ficar definitivo, corrija também na sua planilha.

Telefone é validado antes de gravar e salvo já normalizado. Trocar o telefone de alguém
zera a validação de WhatsApp daquela pessoa — rode **Validar números** de novo.

### Uma pessoa em várias empresas

Cada combinação de empresa + contato é um registro próprio. A mesma pessoa em duas
empresas recebe dois comunicados, um com cada marca.

---

## 3. As variáveis `{}`

Funcionam em **qualquer** campo de texto da tela: etiqueta do topo, assunto, título,
saudação, mensagem e link do botão.

| Variável          | Vira                                            | Exemplo                          |
|-------------------|--------------------------------------------------|----------------------------------|
| `{empresa}`       | Nome da empresa daquele funcionário              | `Padaria São João`               |
| `{nome}`          | Nome completo do funcionário                     | `Maria Silva`                    |
| `{primeiro_nome}` | Só o primeiro nome                               | `Maria`                          |
| `{virgula_nome}`  | `, Maria` — **ou nada**, se a planilha não tiver nome | `Olá{virgula_nome}!` → `Olá, Maria!` ou `Olá!` |

`{virgula_nome}` existe para a saudação não ficar quebrada (`Olá , !`) quando a planilha
vem só com email e empresa. Use ele em vez de escrever `Olá, {primeiro_nome}!`.
Ele engole o espaço que vier antes, então `Olá {virgula_nome}!` e `Olá{virgula_nome}!`
dão o mesmo resultado: `Olá, Maria!`.

**Maiúscula não importa:** `{Empresa}`, `{EMPRESA}` e `{empresa}` funcionam igual.
(`{EMPRESA}` continua saindo em CAIXA ALTA — é a única com efeito próprio.)

**Nome de variável errado** não dá erro: fica literal no email. A tela avisa em vermelho
quando encontra uma que não existe, e a prévia mostra exatamente como vai sair.

### Como o nome da empresa aparece

**Exatamente como está na planilha.** `MRC` continua `MRC`, `PADARIA DO JOÃO` continua
`PADARIA DO JOÃO`, `Mercado Central` continua `Mercado Central`.

O sistema não "arruma" maiúsculas: muita razão social é sigla ou iniciais de nome de
pessoa, e uma correção automática transformaria `MRC` em `Mrc`. Quem digita a planilha
decide como o nome aparece. A única coisa que fazemos é remover espaço sobrando.

Vale para os dois canais e para todos os lugares onde o nome aparece: assunto, cabeçalho
do email, saudação, rodapé, nome do remetente e a imagem do WhatsApp.

Se quiser forçar CAIXA ALTA em algum ponto específico, use `{EMPRESA}` em vez de `{empresa}`.

---

## 4. Formatação da mensagem

O campo **Mensagem** é texto simples. Poucas regras, de propósito:

| Você escreve            | Sai como                          |
|-------------------------|-----------------------------------|
| linha em branco         | parágrafo novo                    |
| `## Como participar`    | subtítulo em azul (mesma caixa)   |
| `- item`                | item de lista com marcador dourado |
| `**importante**`        | **negrito** em azul               |
| `https://site.com`      | link clicável                     |

Exemplo:

```
Time da {empresa}, a campanha anual de vacinação começa na segunda.

## Como participar
- procure o RH do seu turno
- leve documento com foto
- o atendimento vai até as 17h

Dúvidas? Fale com **Ana Costa**, ramal 214.
```

Subtítulo, lista e texto podem estar no mesmo bloco — não precisa separar por linha em branco.

---

## 5. O poster — leia antes de disparar

Esse é o ponto que mais confunde, então a tela mostra em tempo real como o poster vai sair.
São três cenários:

| Situação                                   | Como o funcionário vê                          |
|--------------------------------------------|-------------------------------------------------|
| SMTP configurado + arquivo enviado         | **Arte no corpo do email.** É o que você quer.   |
| URL pública preenchida                     | Arte no corpo, carregada da internet.            |
| Nem SMTP nem URL, só o arquivo             | **Anexo** — o funcionário precisa baixar. Ruim.  |

### Por que isso acontece

A **API do Brevo não sabe embutir imagem** dentro do email. Por ela, ou a imagem está numa
URL pública, ou vira anexo. O **relay SMTP** do Brevo sabe: a arte viaja dentro da mensagem
(`multipart/related`) e aparece no corpo em qualquer cliente de email, sem hospedar nada.

### Como ligar o SMTP (uma vez só)

1. Brevo → canto superior direito → **SMTP & API** → aba **SMTP**
2. Copie o **login SMTP** (algo como `seu-email@smtp-brevo.com`) e gere uma **chave SMTP**
   (começa com `xsmtpsib-`, **não** é a API key `xkeysib-`)
3. No arquivo `.env`, preencha:
   ```
   BREVO_SMTP_LOGIN=seu-login-smtp
   BREVO_SMTP_KEY=xsmtpsib-...
   ```
4. Reinicie o `run.py`
5. Na tela, clique **Testar conexão SMTP** — tem que responder "Conectado em..."

Depois disso, o passo 1 vira só: sobe a imagem, pronto. Ela aparece no corpo.
A logo da SHILD no rodapé também passa a ser embutida, sem precisar de URL pública.

> Na chave SMTP, cuidado com espaço ou quebra de linha coladas junto no copiar/colar —
> um caractere a mais dá erro 535 de autenticação.

### O checkbox "mandar também como anexo"

Só faz diferença quando o poster entra por **URL**. Aí o arquivo vai junto como anexo, de
garantia, caso o email do funcionário bloqueie imagens da internet. Quando o poster está
embutido via SMTP, ele **não** é anexado de novo — não faria sentido.

### Tamanho — resolvido sozinho

Ao subir, a imagem é **otimizada automaticamente**: reduzida para 1200 px de largura
(o dobro dos 600 px do email, para telas retina) e salva no formato que ficar menor.
Um PNG de 3,3 MB exportado do Canva vira ~215 KB, sem diferença visível.

Você não precisa preparar nada — sobe o arquivo original. A tela mostra o antes e depois.

Isso importa porque o poster é enviado uma vez **por funcionário**: 3 MB × 500 pessoas
atrasa o disparo, enche a caixa de todo mundo e piora a nota de spam.

Aceita até 20 MB de entrada. Arquivo com extensão de imagem mas conteúdo inválido é recusado.

> Se você já subiu o poster antes desta versão, **suba de novo** para pegar a otimização.

---

## 6. Links do Google Drive

O link que o Drive dá para compartilhar **não funciona** dentro de `<img>` — ele devolve uma
página, não a imagem. O sistema converte sozinho, então **pode colar o link do Drive direto**,
tanto no poster quanto na coluna `logo` da planilha.

Formatos reconhecidos:

```
https://drive.google.com/file/d/ID/view?usp=sharing
https://drive.google.com/open?id=ID
https://drive.google.com/uc?export=view&id=ID
https://drive.google.com/thumbnail?id=ID&sz=w1000
```

**O que o sistema não pode fazer por você:** o arquivo precisa estar compartilhado como
**"Qualquer pessoa com o link"**. Se ficar como "Restrito", a imagem aparece quebrada para
todo mundo — inclusive na prévia. É a causa nº 1 de logo que não carrega.

Link de qualquer outro site passa intacto, desde que seja o link direto do arquivo de imagem.

---

## 7. Remetente

O endereço é montado como `prefixo@domínio`:

| Campo             | Exemplo               | Resultado                                    |
|-------------------|-----------------------|----------------------------------------------|
| Prefixo           | `comunicados`         | `comunicados@shild.click`                    |
| Domínio           | `shild.click`         | —                                            |
| Nome exibido      | `RH {empresa}`        | `RH Padaria São João`                        |

Marcando **"endereço de origem único por empresa"**, o prefixo ganha o nome da empresa:
`comunicados-padaria-sao-joao@shild.click`. Serve para cada empresa ter uma origem própria
e para separar as respostas.

**Requisito importante:** o domínio `shild.click` precisa estar **autenticado no Brevo**
(SPF/DKIM), não apenas um endereço verificado. Com o domínio autenticado, qualquer prefixo
funciona sem verificar endereço por endereço. Se o Brevo recusar com erro de *sender*,
foi isso — autentique o domínio em Brevo → **Senders, Domains & Dedicated IPs**.

As respostas dos funcionários vão para o `MAIL_REPLY_TO` do `.env`, não para o endereço de
origem. Hoje está `mfontenele.shild@gmail.com`.

---

## 8. Ordem de trabalho recomendada

1. **Poster** — sobe a imagem; confira o aviso verde/vermelho logo abaixo
2. **Conteúdo** — assunto, título, mensagem
3. **Lista** — importa o CSV/XLSX; confira na tabela de empresas se alguma está com logo "faltando"
4. **Remetente** — confira a linha "Exemplo do que o funcionário vê"
5. **Prévia** — a prévia mostra exatamente o que vai ser enviado, inclusive se o poster
   está no corpo ou não
6. **Enviar teste** para você mesmo — **sempre**. Abra no celular e no computador
7. **Disparar campanha**

No passo 7, comece com **Limite de envios = 5** e a empresa mais tolerante selecionada.
Confirme que chegou bem e só então mande para todos.

---

## 9. Quem recebe — os três modos

| Modo                          | Manda para                                        |
|-------------------------------|---------------------------------------------------|
| Somente pendentes             | Quem ainda não recebeu. **É o modo normal.**       |
| Pendentes + que deram erro    | Inclui quem falhou antes. Use para reprocessar.    |
| Todos da base (reenvia)       | Todo mundo, **inclusive quem já recebeu**. Cuidado.|

"Limitar a uma empresa" cruza com o modo: dá para disparar empresa por empresa.

**Resetar status** apaga o histórico **desta campanha** (a tag atual) e volta todo mundo
para "pendente". Não mexe na planilha nem em outras campanhas.

Para tirar alguém da base: tire da planilha e reimporte (ele fica inativo), ou desmarque
a empresa inteira no passo 4.

---

## 10. Campanha nova com a mesma lista

1. Troque a **tag da campanha** (passo 4). Se não trocar, as aberturas da campanha antiga
   se misturam com as da nova
2. Clique **Resetar status** (passo 3)
3. Troque poster, título e mensagem
4. Envie um teste e dispare

---

## 11. Resultados

**Sincronizar com o Brevo** busca os eventos e preenche entregas, aberturas, cliques e bounces.
Os números só aparecem depois de sincronizar — não é automático.

Aberturas levam de minutos a horas para aparecer. Taxa de abertura entre 20% e 40% é normal
para comunicação interna; abaixo de 10% costuma indicar que o email foi para spam.

A busca por tag é tentada primeiro; se não voltar nada, o sistema puxa os eventos recentes e
casa pelo endereço de email. Só atualiza quem está na sua base.

Coluna **Obs.** na tabela mostra o motivo do erro de quem falhou.

---

## 12. Problemas comuns

| Sintoma                                       | Causa provável                                                          |
|-----------------------------------------------|--------------------------------------------------------------------------|
| Poster chegou como anexo                      | SMTP não configurado e sem URL pública. Ver seção 5                       |
| Logo da empresa quebrada                      | Arquivo no Drive não está como "qualquer pessoa com o link"               |
| Logo quebrada só para uma empresa             | Link errado ou vazio naquela linha da planilha. Ver coluna Logo na tabela |
| `{alguma_coisa}` literal no email             | Nome de variável errado — a tela avisa em vermelho. Ver seção 3           |
| Poster some da prévia                         | Ele vai como anexo. A prévia mostra a verdade. Ver seção 5                |
| Erro de *sender* no disparo                   | Domínio não autenticado no Brevo. Ver seção 7                             |
| Erro 535 no teste SMTP                        | Chave SMTP errada, ou espaço/quebra de linha colada junto                 |
| "Não encontrei a coluna de email"             | Cabeçalho da planilha com nome não reconhecido. Ver seção 2               |
| Aberturas zeradas                             | Não sincronizou, ou a campanha é recente demais                           |
| Envio muito lento                             | Normal: 1,5 s entre emails, para proteger a reputação do domínio          |

O intervalo entre envios é o `SEND_DELAY_SECONDS` do `.env`. 1000 funcionários levam
uns 25 minutos. Não abaixe abaixo de 1 segundo.

---

## 13. Limites do Brevo

O plano gratuito tem cota diária de envio. Se estourar no meio do disparo, os que faltaram
ficam com status de erro — no dia seguinte, use o modo **"Pendentes + que deram erro"** para
completar. Nada se perde.

---

## 14. O `.env`

Guarda as credenciais. **Não versione e não mande por email** — a chave do Brevo dá acesso
à conta de envio inteira.

| Variável                 | Para que serve                                              |
|--------------------------|-------------------------------------------------------------|
| `BREVO_API_KEY`          | Envio pela API (`xkeysib-`) e leitura das aberturas/cliques |
| `BREVO_SMTP_LOGIN`/`_KEY`| Envio pelo SMTP — o que embute a imagem no corpo             |
| `TRANSPORTE`             | `auto` (recomendado), `smtp` ou `api`                        |
| `MAIL_REPLY_TO`          | Para onde vão as respostas dos funcionários                  |
| `MAIL_UNSUBSCRIBE_EMAIL` | Descadastro no rodapé                                        |
| `MAIL_TEST_TO`           | Preenche o campo de email de teste                           |
| `SEND_DELAY_SECONDS`     | Intervalo entre envios                                       |
| `EMAIL_LOGO_URL`         | Logo SHILD por URL. Desnecessário com SMTP ligado            |
| `PORT`                   | 8010 — diferente do Prospector_email (8000), rodam juntos    |

---
---

# WhatsApp

Segunda aba do sistema (`http://127.0.0.1:8010/whatsapp`). Mesma campanha, outro canal.
Base própria, transporte próprio, ritmo próprio — o envio por email não é afetado.

## 15. O que o funcionário recebe

**Uma imagem só**, montada pelo sistema:

```
+---------------------------------------------+
|   [logo SHILD]   |   [logo da empresa]      |   faixa branca
+---------------------------------------------+
|############ barra dourada #################|
+---------------------------------------------+
|                                             |
|            poster da campanha               |
|                                             |
```

Com a legenda logo abaixo, no formato do WhatsApp.

O cabeçalho é **branco** de propósito: logo de empresa vem em qualquer cor e quase sempre
é desenhada para fundo claro — sobre o azul da SHILD, metade delas sumiria.

Se a logo da empresa não carregar (link privado, 404), entra o **nome da empresa** escrito
em azul, e o envio continua. A tela avisa qual empresa caiu nesse caso.

A imagem é composta **uma vez por empresa** e reaproveitada para todos os funcionários dela.
O botão **Recompor todas** limpa esse cache — use depois de trocar o poster.

## 16. Configurar a Evolution API

No `.env`:

```
EVOLUTION_API_URL=https://evo.seudominio.com.br
EVOLUTION_API_KEY=token-da-instancia
EVOLUTION_INSTANCE=nome-da-instancia
```

> Use o token **da instância**, não o token global do servidor.

Reinicie o `run.py` e abra a aba WhatsApp. O passo 1 mostra o estado:

| Estado    | Significa                                                     |
|-----------|---------------------------------------------------------------|
| `open`    | Conectada. Pode disparar.                                      |
| `close`   | Desconectada — leia o QR code no painel da Evolution           |
| `connecting` | Em processo de conexão                                      |
| `erro`    | URL, token ou nome da instância errados                        |

## 17. A planilha

A sua **planilha de controle de funcionários serve direto**, sem editar:

```
EMPRESA | LOGO DA EMPRESA | NOME COMPLETO | RG | CPF | EMAIL | TELEFONE | DATA NASC. | DATA INGRESSO
```

O sistema usa **EMPRESA**, **LOGO DA EMPRESA**, **NOME COMPLETO** e **TELEFONE**.
RG, CPF, EMAIL e as datas são ignorados — ficam na planilha sem problema.

Telefone é normalizado sozinho: `(86) 99999-8888`, `86999998888`, `+55 86 99999-8888`
e `5586999998888` viram todos `5586999998888`.

Número sem DDD é recusado, a não ser que você preencha o campo **DDD padrão** na tela
(ou `WA_DDD_PADRAO` no `.env`). Cada linha recusada aparece na tela com o motivo.

## 18. Validar números — faça sempre

O botão **Validar números no WhatsApp** pergunta ao próprio WhatsApp quem existe.

Isso resolve o problema do **nono dígito**: em DDDs a partir de 31, o WhatsApp costuma
guardar o número *sem* o 9 inicial. Adivinhar dá errado com frequência; a validação devolve
o identificador correto e o sistema passa a usar ele no disparo.

De quebra, marca quem não tem WhatsApp — esses são pulados no envio (dá para desmarcar).

Rode a validação **depois de cada importação**.

## 19. O texto

Por padrão o WhatsApp reaproveita **título + saudação + mensagem** do email, convertidos:

| Email             | WhatsApp        |
|-------------------|-----------------|
| `**negrito**`     | `*negrito*`     |
| `## Subtítulo`    | `*Subtítulo*`   |
| `- item`          | `• item`        |

O sistema **não altera maiúsculas** do que você escreveu — nem no título, nem nos
subtítulos, nem no nome da empresa. Se quiser CAIXA ALTA, digite em caixa alta.

As variáveis são as mesmas: `{empresa}`, `{nome}`, `{primeiro_nome}`, `{virgula_nome}`.

O campo **Texto só do WhatsApp** substitui tudo isso quando você quer algo mais curto —
o que costuma ser melhor no WhatsApp. Deixe vazio para reaproveitar o do email.

### Limite de 1024 caracteres

É o tamanho máximo da legenda de uma imagem no WhatsApp. Se o texto passar disso, o sistema
manda **a imagem com o começo do texto e o restante numa segunda mensagem**, cortando em
parágrafo inteiro. A tela mostra a contagem e simula as duas mensagens antes de você disparar.

Para caber em uma mensagem só, escreva um texto de WhatsApp mais curto.

## 20. Ritmo e risco de bloqueio

Disparo rápido em massa é a forma mais comum de um número ser **bloqueado pelo WhatsApp**.

O intervalo padrão é **8 segundos** (`WA_DELAY_SECONDS`). Recomendações:

- Comece com **Limite de envios = 5** e confira se chegou bem
- Aumente aos poucos; não faça centenas de disparos no primeiro dia de uso do número
- Não abaixe o intervalo para menos de 5 segundos
- Use um número dedicado à comunicação interna, não o número pessoal
- É comunicação para os próprios funcionários das empresas administradas — mas mesmo assim,
  quem responder pedindo para sair deve ser removido da base

100 funcionários a 8 s levam pouco mais de 13 minutos.

## 21. Ordem de trabalho

1. **Conexão** — confirme `open`
2. **Imagem** — clique em *Montar prévia* e confira o cabeçalho com as duas logos
3. **Lista** — importe a planilha de RH; confira os telefones recusados
4. **Validar números** — sempre
5. **Enviar teste** para o seu próprio número
6. **Disparar**, começando com limite baixo

## 22. Problemas comuns — WhatsApp

| Sintoma                                  | Causa provável                                                    |
|------------------------------------------|--------------------------------------------------------------------|
| Estado `close`                           | Instância desconectada — leia o QR no painel da Evolution          |
| Estado `erro`                            | URL, token ou nome da instância errados no `.env`                  |
| "Evolution API não configurada"          | Faltam as três variáveis no `.env`, ou não reiniciou o `run.py`    |
| Logo da empresa não aparece na imagem    | Link do Drive não está como "qualquer pessoa com o link"           |
| Nome da empresa no lugar da logo         | Mesma causa acima — o envio continua normalmente                   |
| Muitos telefones recusados               | Coluna sem DDD. Preencha o DDD padrão na tela                      |
| "número sem WhatsApp"                    | A validação não encontrou o número. Confira na planilha            |
| Poster antigo continua aparecendo        | Cache — clique em *Recompor todas*                                 |
| Mensagens pararam de sair                | Número pode ter sido limitado. Pare, espere e reduza o ritmo       |

## 23. Arquivos do WhatsApp

```
app/fones.py        normaliza telefone brasileiro
app/compositor.py   monta a imagem: cabeçalho de marcas + poster
app/whatsapp.py     cliente da Evolution API
app/wa_campaign.py  base própria, validação de números e disparo
app/static/whatsapp.html   a tela
saidas/compostas/   cache das imagens montadas (uma por empresa)
```
