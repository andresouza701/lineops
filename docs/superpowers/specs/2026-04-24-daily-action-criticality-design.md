# Criticidade em Acoes do Dia

Data: 2026-04-24

## Spec Summary

O painel Acoes do Dia deve classificar cada usuario visivel em um nivel de criticidade: baixo, medio ou alto.

A classificacao usa as linhas apresentadas no proprio painel para o usuario, considerando o escopo ja aplicado por role, supervisor, gerente e filtros existentes.

Uma linha com pendencia e uma linha onde as duas condicoes sao verdadeiras:

- status da linha diferente de Ativo
- acao diferente de Sem Acao

## Regra de Classificacao

A regra deve usar precedencia Alto > Medio > Baixo.

- Alto: usuario sem linha, ou todas as linhas do usuario estao com pendencia.
- Medio: usuario com exatamente 2 linhas e exatamente 1 linha com pendencia.
- Baixo: usuario com 2 ou mais linhas e que nao se enquadra nas regras de Alto ou Medio.
- Alto fallback: usuario com apenas 1 linha e sem pendencia, pois nao ha redundancia operacional.

## Gap Analysis

A regra original tinha sobreposicao entre baixo (2+ linhas) e medio (2 linhas com 1 pendencia). A precedencia resolve o conflito: primeiro avalia alto, depois medio, depois baixo.

Casos nao descritos diretamente foram definidos como:

- 3+ linhas com algumas pendencias, mas nao todas: baixo.
- 1 linha ativa sem pendencia: alto.

## API Contract / Service Behavior / Persistence Impact

Nao ha impacto em persistencia. Nenhum novo campo sera salvo no banco.

A classificacao sera calculada em memoria a partir das rows ja carregadas para o painel Acoes do Dia.

O contrato do template passa a receber, por row, metadados de criticidade para exibicao.

## Test Checklist

- Usuario sem linha deve ser alto.
- Usuario com todas as linhas pendentes deve ser alto.
- Usuario com exatamente 2 linhas e exatamente 1 pendente deve ser medio.
- Usuario com 2 ou mais linhas sem pendencias deve ser baixo.
- Usuario com 1 linha ativa sem pendencia deve ser alto.
- Linhas com apenas status diferente de ativo, mas acao sem acao, nao contam como pendencia.
- Linhas com apenas acao diferente de sem acao, mas status ativo, nao contam como pendencia.

## Test Strategy

Criar testes Django cobrindo a funcao de classificacao e a exposicao do resultado no contexto/renderizacao do painel.

## Compliance Report

- Spec definida antes do codigo.
- Testes serao derivados desta spec.
- Implementacao deve manter controller fino e concentrar a regra em funcao isolada testavel.
