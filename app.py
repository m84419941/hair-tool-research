import os, re, json, requests
from urllib.parse import urlparse, parse_qs
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from groq import Groq

st.set_page_config(page_title='Hair Tool Research', page_icon='🔎', layout='wide')
TAVILY=st.secrets.get('TAVILY_API_KEY',os.getenv('TAVILY_API_KEY',''))
GROQ=st.secrets.get('GROQ_API_KEY',os.getenv('GROQ_API_KEY',''))
MODEL=st.secrets.get('GROQ_MODEL',os.getenv('GROQ_MODEL','openai/gpt-oss-20b'))
TAXONOMY=['drying speed','styling speed','curl formation','curl longevity','smoothing','frizz','shine','volume','heat perception','damage perception','noise','weight','balance','grip','controls','attachments','learning curve','hair type','hair length','skill level','price and value','returns']

def tv_search(q,n=8):
    r=requests.post('https://api.tavily.com/search',json={'api_key':TAVILY,'query':q,'search_depth':'advanced','max_results':n,'include_raw_content':True},timeout=90);r.raise_for_status();return r.json().get('results',[])
def video_id(url):
    p=urlparse(url)
    if p.netloc in ('youtu.be','www.youtu.be'): return p.path.strip('/').split('/')[0]
    if 'youtube.com' in p.netloc:
        if p.path=='/watch': return parse_qs(p.query).get('v',[''])[0]
        m=re.search(r'/(shorts|embed)/([^/?]+)',p.path);return m.group(2) if m else ''
    return ''
def transcript(url):
    vid=video_id(url)
    if not vid:return ''
    try:return ' '.join(x.text for x in YouTubeTranscriptApi().fetch(vid,languages=['en','en-GB','en-US']))[:12000]
    except Exception:return ''
def collect(product):
    qs=[f'"{product}" review hair tool customer experience',f'"{product}" review site:youtube.com',f'"{product}" reviews retailer hair',f'"{product}" problems reddit forum']
    seen=set();out=[]
    for q in qs:
        for x in tv_search(q):
            u=x.get('url','')
            if not u or u in seen:continue
            seen.add(u); txt=(x.get('raw_content') or x.get('content') or '')
            kind='YouTube' if video_id(u) else ('Forum' if 'reddit.com' in u.lower() else 'Web')
            if kind=='YouTube': txt=transcript(u) or txt
            if len(txt)<100:continue
            out.append({'id':f'S{len(out)+1}','title':x.get('title') or u,'url':u,'kind':kind,'text':txt})
    return out[:24]
def analyse(product,sources):
    # Search remains broad; AI receives short excerpts from up to 20 sources to stay safely below free 8k TPM.
    evidence='\n\n'.join(f"[{s['id']}] {s['title'][:100]} ({s['kind']})\n{s['text'][:700]}" for s in sources[:20])
    schema={'executive_summary':'string','positives':[{'finding':'string','detail':'string','source_ids':['S1']}],'frustrations':[{'finding':'string','detail':'string','source_ids':['S1']}],'hair_type_insights':[{'group':'string','finding':'string','source_ids':['S1']}],'themes':[{'theme':'string','direction':'positive|negative|mixed','strength':'high|medium|low','source_ids':['S1']}],'comparisons':[{'product':'string','finding':'string','source_ids':['S1']}],'opportunities':[{'opportunity':'string','rationale':'string','source_ids':['S1']}],'limitations':['string']}
    prompt=f"""Analyse public evidence about {product}. Use ONLY supplied evidence. Consolidate duplicates. Never invent frequency, hair type, comparison or performance claims. Every finding needs 1-4 source_ids that directly support it. Taxonomy: {', '.join(TAXONOMY)}. Return valid JSON matching: {json.dumps(schema)}\nEVIDENCE:\n{evidence}"""
    r=Groq(api_key=GROQ).chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],response_format={'type':'json_object'},temperature=0.1,max_tokens=1200)
    return json.loads(r.choices[0].message.content)
def links(ids,sm):
    return ' · '.join(f"[{i}: {sm[i]['title'][:55]}]({sm[i]['url']})" for i in ids if i in sm)
def findings(items,sm,title='finding',detail='detail'):
    for x in items:
        st.markdown(f"**{x.get(title,'')}**  \n{x.get(detail,'')}  \nEvidence: {links(x.get('source_ids',[]),sm)}")

st.title('Hair Tool Research');st.caption('Live public web + YouTube evidence synthesis with citations on every finding')
with st.sidebar:
    st.subheader('Live connectors');st.write('Web search:','✅' if TAVILY else '❌ Tavily key needed');st.write('AI synthesis:','✅' if GROQ else '❌ Groq key needed');st.caption('Public competitor data only. YouTube captions are used when available.')
product=st.text_input('Search a product',placeholder='e.g. Shark FlexStyle')
if st.button('Analyse product',type='primary',use_container_width=True):
    if not product.strip():st.error('Enter a product name.');st.stop()
    if not TAVILY or not GROQ:st.error('Add Tavily and Groq keys in Streamlit Secrets.');st.stop()
    with st.status('Collecting live evidence…',expanded=True) as status:
        sources=collect(product.strip());st.write(f'Collected {len(sources)} usable web and YouTube sources.')
        if not sources:st.error('No usable public evidence found.');st.stop()
        st.write('Coding themes and validating citations…')
        try:report=analyse(product.strip(),sources)
        except Exception as e:
            m=str(e).lower()
            if '413' in m or 'request too large' in m or 'tokens per minute' in m or '429' in m or 'rate_limit' in m:
                st.error('The free Groq token/rate allowance is temporarily at its limit. No charge has been made. Wait one minute and try again.');st.stop()
            raise
        status.update(label='Report ready',state='complete',expanded=False)
    sm={s['id']:s for s in sources};st.header(product.strip());st.info(report.get('executive_summary',''))
    a,b=st.columns(2)
    with a:st.subheader('What people value');findings(report.get('positives',[]),sm)
    with b:st.subheader('Main frustrations');findings(report.get('frustrations',[]),sm)
    st.subheader('Hair-type insights');findings(report.get('hair_type_insights',[]),sm,'group','finding')
    st.subheader('Theme map')
    for x in report.get('themes',[]):st.markdown(f"**{x.get('theme','')}** · {x.get('direction','')} · {x.get('strength','')}  \nEvidence: {links(x.get('source_ids',[]),sm)}")
    c,d=st.columns(2)
    with c:st.subheader('Competitor comparisons');findings(report.get('comparisons',[]),sm,'product','finding')
    with d:st.subheader('White-space signals');findings(report.get('opportunities',[]),sm,'opportunity','rationale')
    st.subheader('Source library')
    for s in sources:st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
    if report.get('limitations'):st.warning('Limitations: '+'; '.join(report['limitations']))
