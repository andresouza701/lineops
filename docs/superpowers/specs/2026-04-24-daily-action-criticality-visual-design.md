# Destaque visual por criticidade em Acoes do Dia

Data: 2026-04-24

## Spec Summary

O painel Acoes do Dia deve destacar visualmente cada linha de pendencia conforme a criticidade ja calculada para o usuario: alto, medio ou baixo.

## Gap Analysis

A criticidade ja existe no contexto da row, mas o destaque atual depende principalmente do badge textual. Em tabelas densas, isso dificulta priorizacao rapida.

## Design aprovado

Usar a abordagem 3: faixa lateral + fundo leve + badge.

- Alto: faixa lateral vermelha, fundo vermelho suave e badge vermelho.
- Medio: faixa lateral ambar, fundo amarelo suave e badge amarelo.
- Baixo: faixa lateral verde, fundo verde suave e badge verde.

## API Contract / Service Behavior / Persistence Impact

Nao ha alteracao de persistencia nem Docker.

O contrato de row passa a incluir uma classe CSS de criticidade para a linha, derivada do nivel ja calculado.

## Test Checklist

- Row alto deve renderizar classe visual de alto.
- Row medio deve renderizar classe visual de medio.
- Row baixo deve renderizar classe visual de baixo.
- O badge textual deve continuar presente.
- Hover da tabela nao deve remover o destaque.

## Test Strategy

Adicionar assertivas de renderizacao no teste do painel e manter os testes de classificacao existentes.

## Compliance Report

- Spec visual definida antes do codigo.
- Nao ha impacto de banco, migrations ou Docker.
- Mudanca restrita a view/template/testes.
