import os

import json

from datetime import datetime

import openai

import psycopg2

from psycopg2.extras import RealDictCursor

import time

from typing import Dict, Any

def get_db_connection():
    while True:
        try:
            return psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "db"),
                database=os.getenv("POSTGRES_DB", "teste_guia"),
                user=os.getenv("POSTGRES_USER", "teste_guia"),
                password=os.getenv("POSTGRES_PASSWORD", "teste_guia")
            )
        except psycopg2.OperationalError:
            print("Waiting for database...")
            time.sleep(2)

def format_messages_for_analysis(messages):
    formatted = []
    
    formatted.append({
        "role": "system",
        "content": "A seguir está uma conversa entre um cliente (user) e uma assistente de atendimento (assistant) de um motel."
    })
    
    for msg in messages:
        if not msg.get("content") or not isinstance(msg.get("content"), str):
            continue
            
        content = msg["content"].replace("<PHOTO>", "[Foto]")
        content = content.replace("<CONTATO", "[Contato:")
        content = content.replace(">", "]")
        
        role = "user" if msg["remote"] else "assistant"
        formatted.append({"role": role, "content": content})
    
    return formatted

def analyze_conversation(messages: list, session_id: int) -> Dict[str, Any]:
    print(f"\nAnalyzing session {session_id} with {len(messages)} messages...")
    
    print("Formatting messages for analysis...")
    formatted_messages = [
        {"role": "system", "content": """You are an AI conversation analyzer. Analyze the conversation and return a JSON object with the following structure:
            {
                "summary": "Brief summary of the conversation",
                "main_topics": ["List of main topics discussed"],
                "sentiment": "Overall sentiment (positive/negative/neutral)",
                "key_points": ["List of key points or decisions made"]
            }
            Respond ONLY with the JSON object, no additional text."""},
        {"role": "user", "content": f"Analyze this conversation: {str(messages)}"}
    ]

    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            print("Sending request to OpenAI API...")
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=formatted_messages,
                temperature=0.7,
                max_tokens=500
            )
            
            print("Parsing OpenAI response...")
            content = response.choices[0].message['content'].strip()
            
            if not content.startswith('{'):
                content = '{' + content
            if not content.endswith('}'):
                content = content + '}'
                
            return json.loads(content)
            
        except openai.error.RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                print(f"Rate limit reached. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            raise
        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                print(f"JSON decode error. Retrying... (Attempt {attempt + 1}/{max_retries})")
                continue
            raise
        except Exception as e:
            print(f"Error analyzing session {session_id}: {str(e)}")
            print(f"Error type: {type(e)}")
            raise

    raise Exception(f"Failed to analyze session {session_id} after {max_retries} attempts")

def save_analysis(session_id, analysis):
    conn = get_db_connection()
    cur = conn.cursor()
    
    sentiment_map = {
        "negative": 3,
        "neutral": 5,
        "positive": 8
    }
    satisfaction = sentiment_map.get(analysis.get("sentiment", "neutral"), 5)
    
    improvements = []
    if analysis.get("main_topics"):
        improvements.extend(analysis["main_topics"])
    if analysis.get("key_points"):
        improvements.extend(analysis["key_points"])
    improvement_text = ". ".join(improvements)
    
    cur.execute("""
        INSERT INTO analysis (
            session_id,
            satisfaction,
            summary,
            improvement,
            created_at
        ) VALUES (%s, %s, %s, %s, %s)
    """, (
        session_id,
        satisfaction,
        analysis.get("summary", ""),
        improvement_text,
        datetime.now()
    ))
    
    conn.commit()
    cur.close()
    conn.close()

def process_pending_conversations():
    conn = None
    try:
        print("\nConnecting to database...", flush=True)
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("Querying for unanalyzed sessions...", flush=True)
        cur.execute("""
            SELECT s.id as session_id, 
                   json_agg(json_build_object(
                       'content', m.content,
                       'remote', m.remote,
                       'created_at', m.created_at
                   ) ORDER BY m.created_at) as messages,
                   COUNT(*) as msg_count
            FROM session s
            JOIN message m ON s.id = m.session_id
            LEFT JOIN analysis a ON s.id = a.session_id
            WHERE a.id IS NULL
            GROUP BY s.id
            HAVING COUNT(*) > 1
        """)
        
        sessions = cur.fetchall()
        
        print(f"Found {len(sessions)} sessions to analyze", flush=True)
        
        for session in sessions:
            try:
                print(f"\nAnalyzing session {session['session_id']} with {session['msg_count']} messages...", flush=True)
                result = analyze_conversation(session['messages'], session['session_id'])
                if result:
                    print(f"Session {session['session_id']} analyzed successfully", flush=True)
                    sentiment_map = {
                        "negative": 3,
                        "neutral": 5,
                        "positive": 8
                    }
                    satisfaction = sentiment_map.get(result.get("sentiment", "neutral"), 5)
                    print(f"Satisfaction: {satisfaction}/10", flush=True)
                    save_analysis(session['session_id'], result)
            except Exception as e:
                print(f"Error processing session {session['session_id']}: {str(e)}", flush=True)
                continue
        
    except Exception as e:
        print(f"Error in process_pending_conversations: {str(e)}", flush=True)
    finally:
        if conn:
            conn.close()

def call_openai_with_retry(client, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            return response
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"Error calling OpenAI API (attempt {attempt + 1}/{max_retries}): {str(e)}")
            time.sleep(2 ** attempt)

if __name__ == "__main__":
    while True:
        process_pending_conversations()
        time.sleep(30)