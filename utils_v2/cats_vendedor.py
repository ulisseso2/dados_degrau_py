# -*- coding: utf-8 -*-
"""
cats_vendedor.py — SHIM de retrocompatibilidade.
As categorias canônicas agora vivem em utils.venda_consultiva_core (fonte
única da régua). Este módulo apenas reexporta para não quebrar imports
existentes (analise_chats.py e afins).
"""
from utils.venda_consultiva_core import _CATS_VENDEDOR, _CATS_LEGACY  # noqa: F401
