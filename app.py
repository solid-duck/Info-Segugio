import json
import chainlit as cl
from openai import OpenAI
from config import Config
from tavily import TavilyClient
from prompts import query_writer_instructions, summarizer_instructions, reflection_instructions

client = OpenAI(base_url=Config.AI_API_URL, api_key=Config.AI_API_KEY)

def llm(developer_prompt, user_promt, temperature=0, json_mode=True):
    messages = [
        {"role": "system", "content": developer_prompt},
        {"role": "user", "content": user_promt},
    ]
    
    if json_mode:
        response = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"}
        )
    else:
        response = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=messages,
            temperature=temperature
        )
        
    return response.choices[0].message.content

def optmize_search_query(research_query):
    formatted_instructions = query_writer_instructions.format(research_topic=research_query)
    result = llm(formatted_instructions, "genera una query web ottimizzata", temperature=0, json_mode=True)
    obj = json.loads(result)
    return obj

def format_content(result):
    return f"Titolo: {result['title']}\nURL: {result['url']}\n\n Contenuto:\n{result['content']}"

def web_search(search_query):
    tavily_api_key = "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"
    max_results = 10
    include_raw = False

    tavily_client = TavilyClient(api_key=tavily_api_key)
    response = tavily_client.search(
        query=search_query, 
        max_results=max_results, 
        include_raw_content=include_raw
    )
    results = response.get("results", [])
    titles = [result['title'] for result in results]
    contents = [format_content(result) for result in results]
    return {
        "sources_gathered": titles,
        "web_research_results": contents
    }

def summarize_sources(web_research_results, research_topic, running_summary=None):
    # current_results = web_research_results[-1]
    current_results = "\n".join(web_research_results) 
    if running_summary:
        message = (
            f"Estendi questo riassunto: {running_summary}\n\n"
            f"Con questi nuovi risultati: {current_results}\n"
            f"Sul tema: {research_topic}"
        )
    else:
        message = (
            f"Genera un riassunto di questi risultati: {current_results}\n"
            f"Sul tema: {research_topic}"
        )

    return llm(summarizer_instructions, message, temperature=0.2, json_mode=False)

def reflect_on_summary(research_topic, running_summary):
    result = llm(
        reflection_instructions.format(research_topic=research_topic),
        f"Identifica una lacuna e genera una domanda per approfondire il riassunto: {running_summary}",
        temperature=0,
        json_mode=True
    )
    return json.loads(result)

@cl.on_message
async def main(message: cl.Message):
    user_message = message.content
    osq = optmize_search_query(user_message)
    
    query, aspect, reason = osq["query"], osq["aspect"], osq["reason"]
    await cl.Message(content=f"Query ottimizzata: {query}. Aspetto: {aspect}. Motivazione: {reason}").send()

    running_summary = None
    max_cycles = 4

    while True:
        results = web_search(query)

        titles = "\n".join(results["sources_gathered"][0])

        await cl.Message(
            content=f"Fonti trovate: {titles}"
        ).send()

        summary = summarize_sources(results["web_research_results"], query, running_summary)
        running_summary = summary
        
        await cl.Message(
            content=f"Riassunto attuale: {summary}"
        ).send()

        max_cycles -= 1
        if max_cycles <= 0:
            break

        ros = reflect_on_summary(query, summary)
        query = ros.get("domanda_approfondimento", f"Dimmi di più su {query}")
        lacuna_conoscenza = ros.get("lacuna_conoscenza", "")

        await cl.Message(
            content=f"**Riflessione:**\n*Lacuna:* {lacuna_conoscenza}\n*Nuova domanda:* {query}"
        ).send()

    await cl.Message(
        author="my_assistant",
        content=f"Risposta alla tua domanda:\n\n{message.content}\n\n**Riassunto finale:**\n{running_summary}"
    ).send()