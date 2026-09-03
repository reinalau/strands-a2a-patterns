# Strands Agents - A2A

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)
![Strands Agents](https://img.shields.io/badge/Strands_Agents-Framework-FF9900?style=flat&logo=amazonaws&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-000000?style=flat&logo=ollama&logoColor=white)
![Gemma](https://img.shields.io/badge/Gemma-gemma4:e2b--it--qat-4285F4?style=flat&logo=google&logoColor=white)
![Gemini](https://img.shields.io/badge/AI-Gemini%203.5%20Flash--Lite-purple?style=flat&logo=google&logoColor=white)
![A2A](https://img.shields.io/badge/A2A-Linux_Foundation-1F6FEB?style=flat&logo=linuxfoundation&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat)

## Introducción

Este repo es el cuarto capítulo de la serie sobre patrones de orquestación multiagente con Strands Agents. Ya recorrimos **agents-as-tools** (un agente que delega en otros agentes-tool, todo dentro del mismo proceso), **swarm** (colaboración par a par con handoffs) y **graph** (flujos con estado y dependencias explícitas entre nodos). A2A rompe con la premisa que compartían los tres: **ya no estamos orquestando agentes que viven en el mismo proceso Python**.

**Agent-to-Agent (A2A)** es un protocolo abierto (no es una invención de Strands ni de AWS) que define cómo los agentes que ejecutan en en procesos, máquinas o incluso organizaciones distintas se **descubren** y se **comunican** entre sí por HTTP/JSON-RPC. Strands no reinventa el protocolo: hace un  *wrapper* con una interfaz familiar para que trabajar con un agente remoto se sienta exactamente igual que trabajar con un agente local. 

Tres piezas hacen ese wrap posible:

- **`A2AAgent`** — el lado cliente. Envolvés el endpoint de un agente remoto y lo invocás con la misma interfaz que usarías con un `Agent` local (`.invoke()`, `.stream_async()`, etc). Puertas para adentro, no ves protocolo: visualizas un agente.
- **`A2AServer`** — el lado servidor. Toma cualquier `Agent` de Strands y lo expone como servicio A2A, publicando automáticamente un *agent card* en `/.well-known/agent-card.json` — el "currículum" del agente: quién es, qué sabe hacer, qué skills tiene.
- **`A2AClientToolProvider`** — la pieza para *discovery* dinámico. En lugar de codear a mano a qué endpoint le hablás, le das a tu agente orquestador un tool que puede descubrir agentes A2A disponibles y decidir en runtime a cuál delegar, en lenguaje natural.

### ¿Cuándo usar A2A?

- Cuando el agente que necesitás **no vive en tu código** — es de otro equipo, otro framework, o directamente un servicio de terceros.
- Cuando necesitás **separar el despliegue**: que un agente escale, se actualice o cambie de modelo sin que el orquestador se entere ni tenga que redeployarse.
- Cuando hay una razón de **negocio o compliance** para que cierto procesamiento ocurra en un proceso/entorno distinto (por ejemplo, datos sensibles que preferís resolver localmente en vez de mandarlos a una API externa).
- Cuando querés armar algo parecido a un **marketplace de agentes**: descubrir capacidades en runtime, no en tiempo de diseño.

❗ **No es la mejor opción si...**
- Todos tus agentes viven en el mismo proceso y no hay ninguna razón real para separarlos — ahí agents-as-tools, swarm o graph van a ser más simples y con menos overhead (no hay HTTP, ni serialización, ni servidores que levantar).
- Necesitás coordinación fina tipo *swarm* con handoffs — al día de hoy A2A no está soportado dentro de ese patrón en Strands.
- La latencia es crítica: cada salto A2A implica una llamada de red real, no una función in-process.

## Casos de uso

Este repo desarrolla dos variantes del mismo protocolo, elegidas para mostrar las dos formas típicas de usar A2A en la práctica:

| | [`privacy-aware-routing`](./privacy-aware-routing) | [`multi-agent-trip-planner`](./multi-agent-trip-planner) |
|---|---|---|
| **Patrón de uso** | Ruteo determinístico | Descubrimiento dinámico |
| **Agentes remotos** | 1 | 3 |
| **Mecanismo** | `A2AAgent` como tool | `A2AClientToolProvider` |
| **¿A quién le hablo?** | Se sabe de antemano | Se descubre en runtime |
| **Escenario** | Datos sensibles se resuelven local (Gemma/Ollama), el resto vía Gemini | Un orquestador delega en 3 especialistas (vuelos, hoteles, itinerario) según la consulta |

Ambos casos corren 100% en local — sin AWS, sin gastar tokens — así que podés levantarlos directo en tu notebook. El detalle completo de cada uno (arquitectura, setup, cómo correrlo) está en el README de su propia carpeta: [`privacy-aware-routing`](./privacy-aware-routing) y [`multi-agent-trip-planner`](./multi-agent-trip-planner).

## Referencias

- [Strands Agents — Agent-to-Agent (A2A) Protocol](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agent-to-agent/)
- [A2A Protocol — Documentación oficial](https://a2aproject.github.io/A2A/latest/)
- [A2A GitHub Organization](https://github.com/a2aproject/A2A)
- [Ollama — Gemma 4](https://ollama.com/library/gemma4)
- [Artículo relacionado](https://builder.aws.com/content/3IEOXhwX9PxCQwxhggtL5jsD1WJ/a2a-en-strands-agentes-remotos-con-routing-deterministico-y-discovery-dinamico)


## Licencia

Este proyecto está bajo la Licencia MIT. Consultá el archivo [LICENSE](LICENSE) para más detalles.