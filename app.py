import os, re, json, requests
from urllib.parse import urlparse, parse_qs
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from groq import Groq

st.set_page_config(page_title='Hair Tool Research', page_icon='🔎', layout='wide')
st.markdown('''<style>
.stApp{background:#f7f3f7}.block-container{max-width:1200px}.finding{background:white;border-radius:14px;padding:14px 16px;margin:9px 0;border-left:5px solid #936196;box-shadow:0 4px 14px #4327460b}.positive{border-left-color:#4e9d68}.negative{border-left-color:#c65f67}.evidence{font-size:.85rem;color:#6f6672}.pill{display:inline-block;background:#ebdfec;border-radius:999px;padding:5px 9px;margin:3px;font-size:.82rem}</style>''', unsafe_allow_html=True)

TAVILY = st.secrets.get('TAVILY_API_KEY', os.getenv('TAVILY_API_KEY',''))
GROQ = st.secrets.get('GROQ_API_KEY', os.getenv('GROQ_API_KEY',''))
MODEL = st.secrets.get('GROQ_MODEL', os.getenv('GROQ_MODEL','openai/gpt-oss-20b'))

TAXONOMY = ['drying speed','styling speed','curl formation','curl longevity','smoothing','frizz','shine','volume','heat perception','damage perception','noise','weight','balance','grip','controls','attachments','learning curve','hair type','hair length','skill level','price and value','returns']

def tv_search(query, max_results=10):
    r=requests.post('https://api.tavily.com/search',json={'api_key':TAVILY,'query':query,'search_depth':'advanced','max_results':max_results,'include_raw_content':True},timeout=90)
    r.raise_for_status(); return r.json().get('results',[])

def video_id(url):
    p=urlparse(url)
    if p.netloc in ('youtu.be','www.youtu.be'): return p.path.strip('/').split('/')[0]
    if 'youtube.com' in p.netloc:
        if p.path=='/watch': return parse_qs(p.query).get('v',[''])[0]
        m=re.search(r'/(shorts|embed)/([^/?]+)',p.path)
        if m:return m.group(2)
    return ''

def transcript(url):
    vid=video_id(url)
    if not vid:return ''
    try:
        fetched=YouTubeTranscriptApi().fetch(vid,languages=['en','en-GB','en-US'])
        return ' '.join(x.text for x in fetched)[:24000]
    except Exception:return ''

def collect(product):
    queries=[
      f'"{product}" review hair tool customer experience',
      f'"{product}" review site:youtube.com',
      f'"{product}" reviews retailer hair',
      f'"{product}" problems reddit forum'
    ]
    seen=set(); sources=[]
    for q in queries:
        for x in tv_search(q,8):
            url=x.get('url','')
            if not url or url in seen:continue
            seen.add(url)
            text=(x.get('raw_content') or x.get('content') or '')[:24000]
            kind='YouTube' if video_id(url) else ('Forum' if 'reddit.com' in url.lower() else 'Web')
            if kind=='YouTube':
                t=transcript(url)
                if t:text=t
            if len(text)<100:continue
            sources.append({'id':f'S{len(sources)+1}','title':x.get('title') or url,'url':url,'kind':kind,'text':text})
    return sources[:24]

def analyse(product,sources):
    evidence='\n\n'.join(f"[{s['id']}] {s['title']} ({s['kind']})\n{s['text'][:1800]}" for s in sources[:18])
    schema={
      'executive_summary':'string','positives':[{'finding':'string','detail':'string','source_ids':['S1']}],
      'frustrations':[{'finding':'string','detail':'string','source_ids':['S1']}],
      'hair_type_insights':[{'group':'string','finding':'string','source_ids':['S1']}],
      'themes':[{'theme':'string','direction':'positive|negative|mixed','strength':'high|medium|low','source_ids':['S1']}],
      'comparisons':[{'product':'string','finding':'string','source_ids':['S1']}],
      'opportunities':[{'opportunity':'string','rationale':'string','source_ids':['S1']}],
      'limitations':['string']}
    prompt=f'''You are a rigorous product insights researcher analysing public evidence about {product}.
Use only the supplied evidence. Do not turn absence of evidence into a finding. Separate reviewer claims from measured facts. Consolidate duplicates. Every finding MUST have 1-4 valid source_ids that directly support it. Prefer agreement across independent sources. Flag hair-type evidence only when explicitly stated. Taxonomy: {', '.join(TAXONOMY)}.
Return strict JSON matching this schema: {json.dumps(schema)}\n\nEVIDENCE:\n{evidence}'''
    client=Groq(api_key=GROQ)
    r=client.chat.completions.create(model=MODEL,messages=[{'role':'user','content':prompt}],response_format={'type':'json_object'},temperature=0.1)
    return json.loads(r.choices[0].message.content)

def links(ids,source_map):
    good=[source_map[i] for i in ids if i in source_map]
    return ' · '.join(f"[{s['id']}: {s['title'][:60]}]({s['url']})" for s in good)

def cards(items, source_map, css, title_key='finding', detail_key='detail'):
    for it in items:
        st.markdown(f"<div class='finding {css}'><b>{it.get(title_key,'')}</b><br>{it.get(detail_key,'')}</div>",unsafe_allow_html=True)
        st.markdown('**Evidence:** '+links(it.get('source_ids',[]),source_map))

st.title('Hair Tool Research')
st.caption('Live web + YouTube evidence synthesis with citations on every finding')
with st.sidebar:
    st.subheader('Live connectors')
    st.write('Web search:', '✅' if TAVILY else '❌ Tavily key needed')
    st.write('AI synthesis:', '✅' if GROQ else '❌ Groq key needed')
    st.caption('YouTube transcripts are retrieved when public captions are available.')
product=st.text_input('Search a product',placeholder='e.g. Shark FlexStyle')
run=st.button('Analyse product',type='primary',use_container_width=True)
if run:
    if not product.strip():st.error('Enter a product name.')
    elif not TAVILY or not GROQ:st.error('Add TAVILY_API_KEY and GROQ_API_KEY in .streamlit/secrets.toml. See README.')
    else:
        with st.status('Collecting live evidence…',expanded=True) as status:
            sources=collect(product.strip()); st.write(f'Collected {len(sources)} usable web and YouTube sources.')
            if not sources:st.stop()
            st.write('Coding themes and validating citations…'); report=analyse(product.strip(),sources); status.update(label='Report ready',state='complete',expanded=False)
        sm={s['id']:s for s in sources}
        st.header(product.strip()); st.info(report.get('executive_summary',''))
        a,b=st.columns(2)
        with a:st.subheader('What people value');cards(report.get('positives',[]),sm,'positive')
        with b:st.subheader('Main frustrations');cards(report.get('frustrations',[]),sm,'negative')
        st.subheader('Hair-type insights')
        for x in report.get('hair_type_insights',[]):
            st.markdown(f"**{x.get('group','')}**: {x.get('finding','')}  \nEvidence: {links(x.get('source_ids',[]),sm)}")
        st.subheader('Theme map')
        for x in report.get('themes',[]):
            st.markdown(f"<span class='pill'>{x.get('theme')} · {x.get('direction')} · {x.get('strength')}</span>",unsafe_allow_html=True)
            st.markdown('Evidence: '+links(x.get('source_ids',[]),sm))
        c,d=st.columns(2)
        with c:
            st.subheader('Competitor comparisons')
            for x in report.get('comparisons',[]):st.markdown(f"**{x.get('product','')}**: {x.get('finding','')}  \nEvidence: {links(x.get('source_ids',[]),sm)}")
        with d:
            st.subheader('White-space signals')
            for x in report.get('opportunities',[]):st.markdown(f"**{x.get('opportunity','')}**  \n{x.get('rationale','')}  \nEvidence: {links(x.get('source_ids',[]),sm)}")
        st.subheader('Source library')
        for s in sources:st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
        if report.get('limitations'):
            st.warning('Limitations: '+'; '.join(report['limitations']))
