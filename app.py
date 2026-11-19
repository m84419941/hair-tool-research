import os, re, requests
from urllib.parse import urlparse, parse_qs
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from groq import Groq

st.set_page_config(page_title='Hair Tool Research', page_icon='🔎', layout='wide')
TAVILY=st.secrets.get('TAVILY_API_KEY',os.getenv('TAVILY_API_KEY',''))
GROQ=st.secrets.get('GROQ_API_KEY',os.getenv('GROQ_API_KEY',''))
MODEL=st.secrets.get('GROQ_MODEL',os.getenv('GROQ_MODEL','openai/gpt-oss-20b'))

def search(q,n=8):
 r=requests.post('https://api.tavily.com/search',json={'api_key':TAVILY,'query':q,'search_depth':'advanced','max_results':n,'include_raw_content':True},timeout=90);r.raise_for_status();return r.json().get('results',[])
def vid(u):
 p=urlparse(u)
 if p.netloc in ('youtu.be','www.youtu.be'):return p.path.strip('/').split('/')[0]
 if 'youtube.com' in p.netloc:
  if p.path=='/watch':return parse_qs(p.query).get('v',[''])[0]
  m=re.search(r'/(shorts|embed)/([^/?]+)',p.path);return m.group(2) if m else ''
 return ''
def transcript(u):
 v=vid(u)
 if not v:return ''
 try:return ' '.join(x.text for x in YouTubeTranscriptApi().fetch(v,languages=['en','en-GB','en-US']))
 except:return ''
def collect(product):
 qs=[f'"{product}" review hair tool',f'"{product}" review site:youtube.com',f'"{product}" customer reviews retailer',f'"{product}" problems reddit']
 seen=set();out=[]
 for q in qs:
  for x in search(q):
   u=x.get('url','')
   if not u or u in seen:continue
   seen.add(u);kind='YouTube' if vid(u) else ('Forum' if 'reddit.com' in u.lower() else 'Web')
   text=x.get('raw_content') or x.get('content') or ''
   if kind=='YouTube':text=transcript(u) or text
   if len(text)>=100:out.append({'id':f'S{len(out)+1}','title':x.get('title') or u,'url':u,'kind':kind,'text':text})
 return out[:24]
def analyse(product,sources):
 # Smaller payload + output, and non-reasoning instruction for reliable visible completion.
 evidence='\n\n'.join(f"[{s['id']}] {s['title'][:80]}\n{s['text'][:350]}" for s in sources[:14])
 prompt=f'''Using only the evidence below, write a concise Product Insights synthesis for {product}.
Return visible Markdown text, not JSON. Do not provide hidden reasoning. Do not invent frequencies or claims.
Use these headings and at most 2 bullets each:
## Overall picture
## What users value
## Main frustrations
## User / hair-type differences
## Opportunities to investigate
Every bullet MUST finish with source IDs, e.g. [S2, S5]. If evidence is weak, say evidence is limited.
Maximum 450 words.
EVIDENCE:\n{evidence}'''
 r=Groq(api_key=GROQ).chat.completions.create(model=MODEL,messages=[{'role':'system','content':'Answer directly with the requested Markdown synthesis. Do not output reasoning.'},{'role':'user','content':prompt}],temperature=0,max_completion_tokens=1500,reasoning_effort='low',include_reasoning=False)
 text=(r.choices[0].message.content or '').strip()
 if not text:
  # Fallback plain completion with even smaller request.
  evidence='\n\n'.join(f"[{s['id']}] {s['text'][:250]}" for s in sources[:10])
  r=Groq(api_key=GROQ).chat.completions.create(model=MODEL,messages=[{'role':'user','content':f'Summarise {product} in 5 concise evidence-grounded bullets. End every bullet with supporting source IDs. No reasoning. Evidence:\n{evidence}'}],temperature=0,max_completion_tokens=900,reasoning_effort='low',include_reasoning=False)
  text=(r.choices[0].message.content or '').strip()
 if not text:raise ValueError('Groq returned no visible summary text.')
 return text

st.title('Hair Tool Research');st.caption('Live public web + YouTube evidence synthesis')
with st.sidebar:
 st.subheader('Live connectors');st.write('Web search:','✅' if TAVILY else '❌');st.write('AI synthesis:','✅' if GROQ else '❌');st.caption('Public competitor data only. Free-tier limits apply.')
product=st.text_input('Search a product',placeholder='e.g. Shark FlexStyle')
if st.button('Analyse product',type='primary',use_container_width=True):
 if not product.strip():st.error('Enter a product name.');st.stop()
 with st.status('Researching public evidence…',expanded=True) as status:
  sources=collect(product.strip());st.write(f'Collected {len(sources)} usable sources.')
  if not sources:st.stop()
  st.write('Creating cited synthesis…')
  try:report=analyse(product.strip(),sources)
  except Exception as e:st.error('AI synthesis could not complete on the free allowance.');st.code(str(e));st.stop()
  status.update(label='Report ready',state='complete',expanded=False)
 st.header(product.strip());st.subheader('Synthesis');st.markdown(report)
 used=set(re.findall(r'S\d+',report));st.subheader('Evidence links')
 for s in sources:
  if s['id'] in used:st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
 with st.expander('All collected sources'):
  for s in sources:st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
 st.caption('Directional secondary research. Review linked evidence before using findings in decisions.')
