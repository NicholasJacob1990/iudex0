import sys
sys.stdout.flush()
print('Starting...', flush=True)
import openai
print('OpenAI imported', flush=True)
client = openai.OpenAI(api_key='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')
print('Client created', flush=True)
try:
    r = client.chat.completions.create(model='gpt-4o-mini', messages=[{'role': 'user', 'content': 'Say OK'}], max_tokens=10)
    print('RESULT:', r.choices[0].message.content, flush=True)
except Exception as e:
    print('ERROR:', str(e), flush=True)
