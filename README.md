# Campanhas SHILD

Disparo de campanhas para os funcionários das empresas administradas pela SHILD,
em **dois canais independentes**:

| Canal        | Endereço                        | O que o funcionário recebe                              |
|--------------|---------------------------------|----------------------------------------------------------|
| **Email**    | <http://127.0.0.1:8010/>        | Email HTML com a logo da empresa dele e o poster          |
| **WhatsApp** | <http://127.0.0.1:8010/whatsapp>| Uma imagem: `[logo SHILD \| logo da empresa]` + poster    |

Você anexa o **poster**, escreve a **mensagem** e dispara. Os destinatários vêm da sua
**planilha Google de controle de funcionários** — ela é o banco de dados do sistema, e o
que você corrigir pela tela é gravado de volta nela.

O conteúdo da campanha é o mesmo nos dois canais; cada um tem ritmo e status próprios.

**Deploy**: [DEPLOY.md](DEPLOY.md) · **Uso**: [MANUAL.md](MANUAL.md) ·
**Variáveis**: [.env.example](.env.example)

## Arquitetura

```
Planilha Google  ──le/grava──►  aplicação (FastAPI)  ──►  Brevo (email)
 (funcionarios)                        │                   Evolution API (whatsapp)
                                       ▼
                                   Postgres
                     (poster, texto da campanha, status de disparo)
```

Um container só, sem volume: o poster e o texto vivem no banco, então redeploy não perde nada.

Usa a mesma conta Brevo do projeto `Prospector_email` (mesma origem de email), mudando
apenas o prefixo do remetente, o assunto e a tag da campanha.

**Guia completo de uso: [MANUAL.md](MANUAL.md)** — cada campo, cada coluna da planilha
e os problemas comuns.

## Como rodar

```powershell
cd "C:\Users\Matheus Fontenele\Documents\projetos\SHILD\shild-system\RSPV capaign"
.\venv\Scripts\python.exe run.py
```

Abra <http://127.0.0.1:8010>.

Primeira instalação em outra máquina:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # e preencha BREVO_API_KEY
```

## A planilha de funcionários

A sua planilha de controle serve direto, com o cabeçalho na linha 5:

```
EMPRESA | LOGO DA EMPRESA | NOME COMPLETO | RG | CPF | EMAIL | TELEFONE | DATA NASC. | DATA INGRESSO
```

Usa **EMPRESA**, **LOGO DA EMPRESA**, **NOME COMPLETO**, **EMAIL** e **TELEFONE**.
RG, CPF e datas são ignorados. A ordem não importa e o cabeçalho aceita variações
(`e-mail`, `razão social`, `colaborador`, `celular`…).

O botão **Sincronizar com a planilha** traz o estado atual. Linha nova entra, linha alterada
atualiza, linha que sumiu para de receber — sem perder o histórico de quem já recebeu.

Na tabela de destinatários, os campos em azul são editáveis: a correção é gravada
**na célula da planilha**, não só aqui.

## Links de imagem do Google Drive

O link de compartilhamento (`drive.google.com/file/d/ID/view`) **não** funciona dentro de
`<img>` — devolve uma página, não a imagem. O sistema converte sozinho para
`lh3.googleusercontent.com/d/ID`, que os clientes de email carregam.

Só exige que o arquivo esteja compartilhado como **"qualquer pessoa com o link"**.
Isso vale tanto para as logos das empresas quanto para o poster e a logo da SHILD.

## O poster

A API v3 do Brevo não sabe embutir imagem no email — por ela, o poster ou está numa URL
pública, ou vira anexo que o funcionário precisa baixar. O **relay SMTP** do Brevo sabe:
a arte viaja dentro da mensagem (`multipart/related`) e aparece no corpo, sem hospedar nada.

| Situação                              | Como o funcionário vê       |
|---------------------------------------|------------------------------|
| SMTP configurado + arquivo enviado    | **arte no corpo do email**   |
| URL pública preenchida                | arte no corpo, vinda da web  |
| Nem SMTP nem URL, só o arquivo        | **anexo** (precisa baixar)   |

Para ligar o SMTP: Brevo → **SMTP & API** → aba **SMTP**, copie o login e gere uma chave
(`xsmtpsib-`, não a API key `xkeysib-`), preencha `BREVO_SMTP_LOGIN` e `BREVO_SMTP_KEY`
no `.env` e reinicie. O botão **Testar conexão SMTP** confirma. Com SMTP ligado a logo da
SHILD no rodapé também passa a ser embutida, sem precisar de `EMAIL_LOGO_URL`.

A tela mostra em qual dos três casos você está, e a prévia reflete exatamente o que será
enviado.

## Personalização

Em qualquer campo de texto (assunto, título, saudação, mensagem, link do botão):

| variável          | vira                                             |
|-------------------|--------------------------------------------------|
| `{empresa}`       | nome da empresa do funcionário                   |
| `{nome}`          | nome completo do funcionário                     |
| `{primeiro_nome}` | primeiro nome                                    |
| `{virgula_nome}`  | `, Maria` — ou nada, se a lista não tiver o nome |

Maiúscula não importa (`{Empresa}` = `{empresa}`). Variável inexistente é avisada na tela.
O poster é reduzido e comprimido automaticamente no upload — pode subir o arquivo original.

Formatação da mensagem (proposital, poucas regras):

```
linha em branco   -> parágrafo novo
## Assim           -> subtítulo
- assim            -> item de lista
**assim**          -> negrito
https://...        -> vira link sozinho
```

## Remetente por empresa

O remetente é montado como `prefixo@domínio`. Marcando **"endereço de origem único por
empresa"**, vira `prefixo-nome-da-empresa@domínio` — ex. `comunicados-padaria-sao-joao@shild.click`.

O nome exibido também aceita `{empresa}`: `RH {empresa}` → `RH Padaria São João`.

**Requisito:** o domínio (`shild.click`) precisa estar autenticado no Brevo (SPF/DKIM).
Com o domínio autenticado, qualquer prefixo local é aceito sem verificar endereço por endereço.
Se o Brevo recusar com erro de sender, desmarque a opção e use o prefixo único.

## Monitoramento

O botão **Sincronizar com o Brevo** lê os eventos da tag da campanha e preenche
entregas, aberturas, cliques e bounces por destinatário. Use uma **tag diferente
para cada campanha** para os números não se misturarem.

## Arquivos

```
app/config.py       lê as variáveis de ambiente
app/db.py           tabelas e conexão (Postgres em produção, SQLite local)
app/sheets.py       planilha Google: leitura e gravação de célula
app/dados.py        pessoas (espelho da planilha) e envios (status por canal)
app/arquivos.py     poster no banco, materializado em cache quando precisa
app/recipients.py   reconhece as colunas do cabeçalho da planilha
app/links.py        converte links do Drive; slug do nome da empresa
app/fones.py        normaliza telefone brasileiro
app/textfmt.py      mensagem em texto simples -> HTML e -> WhatsApp
app/imagem.py       reduz e comprime o poster no upload (1200 px, formato menor)
app/template.py     monta assunto, HTML, texto e remetente do email
app/mailer.py       API Brevo (envio + eventos de abertura/clique)
app/smtp_mailer.py  relay SMTP do Brevo — imagem embutida no corpo (CID)
app/campaign.py     conteúdo da campanha, plano de envio e disparo por email
app/compositor.py   monta a imagem do WhatsApp (cabeçalho de marcas + poster)
app/whatsapp.py     cliente da Evolution API
app/wa_campaign.py  validação de números e disparo no WhatsApp
app/server.py       FastAPI (API + as duas telas)
app/templates/campanha.html   template do email
app/static/index.html         tela do email
app/static/whatsapp.html      tela do WhatsApp

Dockerfile · docker-compose.yml     deploy no Coolify
saidas/             só cache descartável (imagens montadas), não versionado
```

## WhatsApp (Evolution API)

Usa a sua instância. No `.env`:

```
EVOLUTION_API_URL=https://evo.seudominio.com.br
EVOLUTION_API_KEY=token-da-instancia
EVOLUTION_INSTANCE=nome-da-instancia
```

A **planilha de controle de funcionários serve direto**, com o cabeçalho
`EMPRESA, LOGO DA EMPRESA, NOME COMPLETO, RG, CPF, EMAIL, TELEFONE, DATA NASC., DATA INGRESSO`.
As colunas não usadas são ignoradas.

Antes de disparar, use **Validar números no WhatsApp**: resolve o nono dígito (em DDD ≥ 31
o WhatsApp costuma guardar o número sem o 9) e marca quem não tem WhatsApp.

Intervalo padrão de 8 s entre mensagens. Disparo rápido em massa é a forma mais comum de
um número ser bloqueado — comece com poucos envios.

Detalhes: seções 15 a 23 do [MANUAL.md](MANUAL.md).
#   C A M P A N H A S - S H I L D  
 