# 🚀 Setup Groq - Guia Rápido

## 1️⃣ Criar Conta Groq (2 minutos)

1. Acesse: https://console.groq.com/
2. Clique em **"Sign Up"** ou **"Get Started"**
3. Faça login com:
   - Google
   - GitHub
   - Email

## 2️⃣ Obter API Key (1 minuto)

1. Após login, vá em: https://console.groq.com/keys
2. Clique em **"Create API Key"**
3. Dê um nome (ex: "Análise Transcrições")
4. Copie a chave (começa com `gsk_...`)

⚠️ **IMPORTANTE:** Guarde a chave, ela só aparece uma vez!

## 3️⃣ Configurar no Projeto (30 segundos)

Edite o arquivo `.env`:

```bash
nano .env
```

Adicione/modifique:

```env
GROQ_API_KEY=gsk_sua_chave_aqui
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TEMPERATURE=0.2
GROQ_MAX_TOKENS=1000
```

Salve: `Ctrl+O` → `Enter` → `Ctrl+X`

## 4️⃣ Instalar Biblioteca (10 segundos)

```bash
pip install groq
```

## 5️⃣ Testar Conexão

```bash
python test_groq_connection.py
```

---

## 📊 Modelos Disponíveis (Todos Gratuitos)

| Modelo | Descrição | Velocidade | Qualidade |
|--------|-----------|-----------|-----------|
| `llama-3.3-70b-versatile` | **Recomendado** - Melhor equilíbrio | ⚡⚡⚡ | ⭐⭐⭐⭐⭐ |
| `llama-3.1-8b-instant` | Mais rápido, qualidade boa | ⚡⚡⚡⚡ | ⭐⭐⭐ |
| `mixtral-8x7b-32768` | Contexto grande (32k tokens) | ⚡⚡⚡ | ⭐⭐⭐⭐ |
| `gemma2-9b-it` | Leve e eficiente | ⚡⚡⚡⚡ | ⭐⭐⭐ |

## ⚡ Rate Limits (Grátis)

- **6.000 tokens/minuto**
- **30 requisições/minuto**
- ~**180 análises por hora** (baseado em 1000 tokens/análise)

## 🆚 Groq vs OpenAI

| Recurso | Groq | OpenAI (GPT-4o-mini) |
|---------|------|----------------------|
| **Custo** | 🟢 Grátis | 🟡 ~$0.0003/análise |
| **Velocidade** | 🟢 1-2s | 🟡 2-5s |
| **Qualidade** | 🟢 Muito boa | 🟢 Excelente |
| **Rate Limit** | 🟡 6k tokens/min | 🟢 90k tokens/min (pago) |
| **Privacidade** | 🟡 API externa | 🟡 API externa |

## 🔧 Troubleshooting

### ❌ Erro: "Invalid API Key"
- Verifique se copiou a chave completa
- Confirme que está no `.env` (não `.env.example`)

### ❌ Erro: "Rate limit exceeded"
- Groq limita 6000 tokens/min (grátis)
- Aguarde 1 minuto e tente novamente
- Processe em lotes menores

### ❌ Erro: "Model not found" ou "model_decommissioned"
- Use o modelo mais recente: `llama-3.3-70b-versatile`
- Veja modelos disponíveis: https://console.groq.com/docs/models
- Modelos descontinuados não funcionam mais

---

## ✅ Verificar Instalação

```bash
python -c "from groq import Groq; print('✅ Groq instalado!')"
```

## 🎉 Pronto!

Agora teste na interface:
```bash
streamlit run main.py
```

Vá em **Transcrições** → Clique em **"🤖 Avaliar com IA"**

---

**Tempo total:** ~4 minutos
**Custo:** R$ 0,00 🎉
