import os, re, requests
from urllib.parse import urlparse, parse_qs
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from groq import Groq

st.set_page_config(page_title='Hair Tool Research', page_icon='🔎', layout='wide')
TAVILY = st.secrets.get('TAVILY_API_KEY', os.getenv('TAVILY_API_KEY',''))
GROQ = st.secrets.get('GROQ_API_KEY', os.getenv('GROQ_API_KEY',''))
MODEL = st.secrets.get('GROQ_MODEL', os.getenv('GROQ_MODEL','openai/gpt-oss-20b'))

def search(q, n=8):
    r=requests.post('https://api.tavily.com/search',json={'api_key':TAVILY,'query':q,'search_depth':'advanced','max_results':n,'include_raw_content':True},timeout=90)
    r.raise_for_status(); return r.json().get('results',[])

def vid(url):
    p=urlparse(url)
    if p.netloc in ('youtu.be','www.youtu.be'): return p.path.strip('/').split('/')[0]
    if 'youtube.com' in p.netloc:
        if p.path=='/watch': return parse_qs(p.query).get('v',[''])[0]
        m=re.search(r'/(shorts|embed)/([^/?]+)',p.path); return m.group(2) if m else ''
    return ''

def transcript(url):
    v=vid(url)
    if not v: return ''
    try: return ' '.join(x.text for x in YouTubeTranscriptApi().fetch(v,languages=['en','en-GB','en-US']))
    except Exception: return ''

def collect(product):
    queries=[f'"{product}" review hair tool',f'"{product}" review site:youtube.com',f'"{product}" customer reviews retailer',f'"{product}" problems reddit']
    seen=set(); out=[]
    for q in queries:
        for x in search(q):
            u=x.get('url','')
            if not u or u in seen: continue
            seen.add(u); kind='YouTube' if vid(u) else ('Forum' if 'reddit.com' in u.lower() else 'Web')
            text=x.get('raw_content') or x.get('content') or ''
            if kind=='YouTube': text=transcript(u) or text
            if len(text)<100: continue
            out.append({'id':f'S{len(out)+1}','title':x.get('title') or u,'url':u,'kind':kind,'text':text})
    return out[:24]

def analyse(product,sources):
    # Broad search, compact AI payload. No JSON mode or structured parser.
    evidence='\n\n'.join(f"[{s['id']}] {s['title'][:90]}\n{s['text'][:450]}" for s in sources[:16])
    prompt=f'''Summarise public evidence about {product} for a hair-tool product insights researcher.
Use ONLY the supplied evidence. Do not invent counts, prevalence, hair types, comparisons or measured performance.
Write concise Markdown with exactly these headings:
## Overall picture
## Most consistent positives
## Most consistent frustrations
## Hair-type or user differences
## Product opportunities
Under each heading use no more than 3 bullets. Every bullet must end with supporting source IDs such as [S2] or [S2, S7]. If evidence is insufficient, say so. Keep the whole answer under 650 words.

EVIDENCE:
{evidence}'''
    r=Groq(api_key=GROQ).chat.completions.create(model=MODEL,messages=[{'role':'system','content':'Return concise Markdown only.'},{'role':'user','content':prompt}],temperature=0,max_tokens=900)
    return (r.choices[0].message.content or '').strip()

st.title('Hair Tool Research')
st.caption('Live public web + YouTube evidence synthesis')
with st.sidebar:
    st.subheader('Live connectors')
    st.write('Web search:', '✅' if TAVILY else '❌')
    st.write('AI synthesis:', '✅' if GROQ else '❌')
    st.caption('Public competitor data only. Free-tier limits apply.')

product=st.text_input('Search a product',placeholder='e.g. Shark FlexStyle')
if st.button('Analyse product',type='primary',use_container_width=True):
    if not product.strip(): st.error('Enter a product name.'); st.stop()
    if not TAVILY or not GROQ: st.error('Missing Tavily or Groq key in Streamlit Secrets.'); st.stop()
    with st.status('Researching public evidence…',expanded=True) as status:
        sources=collect(product.strip()); st.write(f'Collected {len(sources)} usable sources.')
        if not sources: st.error('No usable public evidence found.'); st.stop()
        st.write('Creating concise cited synthesis…')
        try: report=analyse(product.strip(),sources)
        except Exception as e:
            m=str(e).lower()
            if any(x in m for x in ['413','429','rate_limit','tokens per minute','request too large']):
                st.error('The free Groq allowance is temporarily at its limit. No charge has been made. Wait one minute and try once more.'); st.stop()
            st.error('The free AI service could not complete this analysis. No charge has been made.')
            with st.expander('Technical detail'): st.code(str(e))
            st.stop()
        status.update(label='Report ready',state='complete',expanded=False)
    st.header(product.strip()); st.markdown(report)
    st.subheader('Evidence links')
    used=set(re.findall(r'S\d+',report))
    for s in sources:
        if s['id'] in used: st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
    with st.expander('All collected sources'):
        for s in sources: st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
    st.caption('This is directional secondary research, not a representative prevalence estimate. Review the linked evidence before using findings in decisions.')
