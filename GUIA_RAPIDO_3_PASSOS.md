# 🚀 GUIA RÁPIDO DE CORREÇÃO - 3 PASSOS

## ✅ CORREÇÕES JÁ APLICADAS NO CÓDIGO

Os seguintes arquivos foram **automaticamente corrigidos**:
- ✅ `_pages/octadesk.py` - Busca base_url corretamente
- ✅ `utils/transcricao_analyzer.py` - Busca openai_api_key do st.secrets

Você não precisa fazer nada no código, apenas seguir os 3 passos abaixo!

---

## 📋 3 PASSOS PARA RESOLVER TUDO

### 🔹 PASSO 1: Atualizar Secrets no Streamlit Cloud (2 minutos)

1. Acesse: https://share.streamlit.io/
2. Clique no seu app → Menu "⋮" → **Settings** → **Secrets**
3. Copie **TODO** o conteúdo do arquivo `SECRETS_STREAMLIT_COMPLETO.toml`
4. Cole no campo de secrets (substituindo tudo)
5. **IMPORTANTE:** Antes de salvar, vá para o Passo 2 para gerar o token do Facebook
6. Atualize o token no campo `access_token` do `[facebook_api]`
7. Clique em **Save**

**O que isso resolve:**
- ✅ Octadesk funcionará
- ✅ Transcrições funcionará (com OpenAI)
- ✅ Facebook funcionará (com o novo token)

---

### 🔹 PASSO 2: Gerar Novo Token do Facebook (3 minutos)

**Método Simples (Recomendado):**

```bash
python gerar_token_rapido.py
```

Siga as instruções na tela:
1. O script abrirá no navegador: https://developers.facebook.com/tools/explorer/
2. Selecione seu App
3. Adicione permissões: `ads_read`, `ads_management`, `business_management`
4. Clique em "Generate Access Token"
5. Copie o token e cole no script
6. O script gerará automaticamente um token de 60 dias!

**Método Manual:**

Se preferir fazer manualmente:
```bash
python generate_facebook_refresh_token.py SEU_TOKEN_AQUI
```

---

### 🔹 PASSO 3: Atualizar o Token nos Secrets (1 minuto)

Depois de gerar o token no Passo 2:

1. Volte aos **Secrets do Streamlit**
2. Encontre a seção `[facebook_api]`
3. Atualize a linha:
   ```toml
   access_token = "COLE_O_NOVO_TOKEN_AQUI"
   ```
4. Clique em **Save**
5. Aguarde o app reiniciar (automático)

---

## ✨ PRONTO! Teste Suas Páginas

Após os 3 passos, teste:

| Página | Status Esperado |
|--------|-----------------|
| 🔗 Octadesk | ✅ Funcionando |
| 📝 Transcrições | ✅ Funcionando |
| 📢 Análise Facebook | ✅ Funcionando |
| 📊 Análise Combinada MKT | ✅ Funcionando |

---

## 🆘 PROBLEMAS?

### Octadesk ainda não funciona?
- Verifique se `base_url` está nos secrets: `https://o198470-a5c.api001.octadesk.services`
- Verifique se `token` está correto

### Transcrições ainda dá erro?
- Verifique se `openai_api_key` está nos secrets
- Verifique se a chave está correta

### Facebook ainda dá erro de token?
- O token pode demorar alguns minutos para propagar
- Aguarde 5 minutos e tente novamente
- Verifique se copiou o token completo (sem espaços extras)
- Se ainda assim não funcionar, gere um novo token

---

## 📁 Arquivos de Referência

- `SECRETS_STREAMLIT_COMPLETO.toml` → Copie para o Streamlit
- `RESUMO_CORRECOES.md` → Detalhes técnicos
- `INSTRUCOES_SECRETS_STREAMLIT.md` → Instruções completas
- `gerar_token_rapido.py` → Script para gerar token

---

## ⚡ Comandos Úteis

```bash
# Gerar token facilmente
python gerar_token_rapido.py

# Verificar expiração do token atual
python verificar_expiracao_token.py

# Verificar permissões
python verificar_permissoes_facebook.py
```

---

## 🎯 Checklist Final

- [ ] Copiei `SECRETS_STREAMLIT_COMPLETO.toml` para o Streamlit
- [ ] Executei `python gerar_token_rapido.py`
- [ ] Atualizei o `access_token` nos secrets
- [ ] Salvei os secrets
- [ ] Aguardei o app reiniciar
- [ ] Testei a página Octadesk
- [ ] Testei a página Transcrições  
- [ ] Testei a página Análise Facebook
- [ ] Testei a página Análise Combinada

---

**💡 Dica:** Salve este guia para referência futura! O token do Facebook expira a cada 60 dias.
