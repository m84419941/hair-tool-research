import os, re, requests
from urllib.parse import urlparse, parse_qs
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from groq import Groq

st.set_page_config(page_title='Hair Tool Research V2', page_icon='🔎', layout='wide')
TAVILY = st.secrets.get('TAVILY_API_KEY', os.getenv('TAVILY_API_KEY',''))
GROQ = st.secrets.get('GROQ_API_KEY', os.getenv('GROQ_API_KEY',''))
MODEL = st.secrets.get('GROQ_MODEL', os.getenv('GROQ_MODEL','openai/gpt-oss-20b'))

SECTIONS = [
    ('Performance', 'Drying/styling speed, curl formation and longevity, smoothing, frizz, shine, volume, root lift, result consistency.'),
    ('Physical Product & Ergonomics', 'Weight, balance, grip, size, manoeuvrability, fatigue, back-of-head reach, cord, storage, build quality.'),
    ('Controls & UI', 'Button placement, visibility, tactile differentiation, accidental presses, icons, settings, feedback, left/right-handed use.'),
    ('Attachments & Mechanisms', 'Changing, securing and storing attachments, heat after use, direction changes, understanding what to use.'),
    ('Sensory Experience', 'Noise and pitch, airflow, heat, vibration, scalp/hair comfort, snagging, pulling, perceived damage.'),
    ('Learning & Usability', 'First use, setup, technique, learning curve, guidance, recreating results and skill progression.'),
    ('Actual Usage Behaviours', 'Starting hair state, routines, sequencing, sectioning, products used, favourite/avoided attachments, touch-ups, companion tools, cleaning and storage. Also capture the job/desired outcome users are trying to achieve and explicit workarounds, abandonment or compromises.'),
    ('User & Hair Context', 'Explicitly stated hair type, strand thickness, density, length, skill level, goal and time available. Never infer missing characteristics.'),
    ('Purchase & Proposition', 'Price and value perception, purchase drivers/barriers, expectations before purchase, competitor consideration, bundle or mix-and-match perceptions, unwanted or missing accessories, return reasons.'),
    ('Ownership & Customer Journey', 'Unboxing and in-box experience, setup, instructions, storage, cleaning, maintenance, reliability, durability, replacement, warranty, support, and first-use versus longer-term ownership.'),
    ('Brand & Communication', 'How people describe the proposition and benefits, claims/messages that shape expectations, expectation-versus-lived-experience gaps, misunderstood features, and natural consumer language. Treat brand claims as context, not proof.'),
    ('Cross-functional Opportunities', 'Evidence-led questions split where relevant across Product, Commercial/Proposition, Customer Journey, and Brand/Communication. Questions only, never unsupported recommendations.')
]

def tavily(q, n=8):
    r=requests.post('https://api.tavily.com/search',json={'api_key':TAVILY,'query':q,'search_depth':'advanced','max_results':n,'include_raw_content':True},timeout=90)
    r.raise_for_status(); return r.json().get('results',[])

def video_id(url):
    p=urlparse(url)
    if p.netloc in ('youtu.be','www.youtu.be'): return p.path.strip('/').split('/')[0]
    if 'youtube.com' in p.netloc:
        if p.path == '/watch': return parse_qs(p.query).get('v',[''])[0]
        m=re.search(r'/(shorts|embed)/([^/?]+)',p.path); return m.group(2) if m else ''
    return ''

def transcript(url):
    v=video_id(url)
    if not v: return ''
    try: return ' '.join(x.text for x in YouTubeTranscriptApi().fetch(v,languages=['en','en-GB','en-US']))
    except Exception: return ''

def source_type(url, title):
    low=(url+' '+title).lower()
    if video_id(url):
        return 'Brand video' if any(x in low for x in ['official','shark beauty','dyson']) else 'YouTube review'
    if 'reddit.com' in low: return 'Forum'
    if any(x in low for x in ['amazon.','bestbuy.','boots.','sephora.','ulta.','currys.']): return 'Retailer/reviews'
    if any(x in low for x in ['sharkclean.','sharkbeauty.','dyson.','ghdhair.','babyliss.']): return 'Brand content'
    return 'Editorial/blog'

@st.cache_data(ttl=21600, show_spinner=False)
def collect(product):
    queries=[
        f'"{product}" review hair tool controls attachments ergonomics',
        f'"{product}" review site:youtube.com hair',
        f'"{product}" customer reviews problems',
        f'"{product}" reddit hair review'
    ]
    seen=set(); out=[]
    for q in queries:
        for x in tavily(q):
            url=x.get('url',''); title=x.get('title') or url
            if not url or url in seen: continue
            seen.add(url)
            text=x.get('raw_content') or x.get('content') or ''
            if video_id(url): text=transcript(url) or text
            if len(text)<100: continue
            out.append({'id':f'S{len(out)+1}','title':title,'url':url,'kind':source_type(url,title),'text':text})
    return out[:24]

def analyse(product, sources):
    # Controlled payload for Groq free tier. Search library remains broader than AI payload.
    evidence='\n\n'.join(f"[{s['id']}] [{s['kind']}] {s['title'][:75]}\n{s['text'][:330]}" for s in sources[:14])
    taxonomy='\n'.join(f'- {name}: {desc}' for name,desc in SECTIONS)
    prompt=f'''Create a concise, evidence-grounded Product Insights report for {product} using ONLY the supplied evidence.

RULES
- Do not infer hair characteristics, prevalence, ownership duration or measured performance.
- Treat brand content as context, not independent user evidence.
- Distinguish first impressions from longer-term use where stated.
- If sources conflict, show the mixed evidence.
- If a category lacks evidence, write "Insufficient evidence in the collected sources."
- Every substantive bullet must end with source IDs such as [S2, S7].
- Cross-functional Opportunities must be questions raised by cited evidence, never unsupported recommendations.
- Keep Product Experience as the deepest analysis. Purchase, journey and brand sections are secondary and should stay concise.
- For bundle/mix-and-match signals, only report consumer perception when explicitly present in evidence. Do not invent bundle demand from price complaints alone.
- Separate expectation/marketing observations from actual product-use observations.
- In Actual Usage Behaviours, explicitly look for: (a) job/desired outcome, (b) workaround, (c) abandonment of a feature/attachment/tool, and (d) compromise accepted because another benefit matters more. Do not create these if they are not evidenced.
- For expectation-versus-lived-experience gaps, identify the expectation source where visible (brand, retailer, influencer/editorial or prior competitor experience) and separately state the reported lived experience.
- Return visible Markdown only. No JSON, hidden reasoning or code fences.

OUTPUT FORMAT
Start with exactly:
## Snapshot
Then 3-5 short bullets covering overall reception, key product strengths, key product frictions, who/context it appears to suit, and only the most important cross-functional signal if strongly evidenced. Maximum 120 words.

Then include each heading exactly once, in this exact order:
{chr(10).join('## '+name for name,_ in SECTIONS)}
Under each heading provide no more than 3 bullets. Each bullet should follow this compact pattern where evidence allows:
**Theme — Positive/Negative/Mixed | Strong/Moderate/Limited evidence**: finding; usage context; relevant product detail. [source IDs]
Do not force every field when it is unknown. Product sections may use up to 3 bullets each. Purchase, Journey, Brand and Cross-functional sections should use no more than 2 bullets each. Total report maximum 1,150 words.

TAXONOMY
{taxonomy}

EVIDENCE
{evidence}'''
    r=Groq(api_key=GROQ).chat.completions.create(
        model=MODEL,
        messages=[{'role':'system','content':'Answer directly with concise Markdown. Do not output reasoning.'},{'role':'user','content':prompt}],
        temperature=0,
        max_completion_tokens=1900,
        reasoning_effort='low',
        include_reasoning=False
    )
    text=(r.choices[0].message.content or '').strip()
    if not text: raise ValueError('The AI returned no visible report text.')
    return text

def split_report(text):
    names=['Snapshot']+[n for n,_ in SECTIONS]
    pattern=r'(?m)^##\s+('+'|'.join(re.escape(n) for n in names)+r')\s*$'
    matches=list(re.finditer(pattern,text))
    result={}
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        result[m.group(1)]=text[m.end():end].strip()
    return result

def cited_ids(text): return set(re.findall(r'\bS\d+\b',text or ''))

st.title('Hair Tool Research V2')
st.caption('Detailed competitor UX and Product Insights from public evidence')
with st.sidebar:
    st.subheader('Live connectors')
    st.write('Web search:', '✅' if TAVILY else '❌')
    st.write('AI synthesis:', '✅' if GROQ else '❌')
    st.caption('Public competitor products only. V1 remains separate and unchanged.')

product=st.text_input('Search a competitor product',placeholder='e.g. Dyson Airwrap Co-anda 2x')
if st.button('Analyse product',type='primary',use_container_width=True):
    if not product.strip(): st.error('Enter a product name.'); st.stop()
    if not TAVILY or not GROQ: st.error('Missing Tavily or Groq key in Streamlit Secrets.'); st.stop()
    with st.status('Researching public evidence…',expanded=True) as status:
        sources=collect(product.strip())
        st.write(f'Collected {len(sources)} usable public sources.')
        if not sources: st.error('No usable public evidence found.'); st.stop()
        st.write('Creating detailed Product Insights synthesis…')
        try: report=analyse(product.strip(),sources)
        except Exception as e:
            msg=str(e).lower()
            if any(x in msg for x in ['413','429','rate_limit','tokens per minute','request too large']):
                st.error('The free Groq allowance is temporarily at its limit. No charge has been made. Wait one minute and try once more.')
            else:
                st.error('The detailed synthesis could not complete. V1 remains unaffected.')
                with st.expander('Technical detail'): st.code(str(e))
            st.stop()
        status.update(label='Report ready',state='complete',expanded=False)

    sections=split_report(report)
    st.header(product.strip())
    kinds={}
    for s in sources: kinds[s['kind']]=kinds.get(s['kind'],0)+1
    st.caption(' · '.join([f'{len(sources)} sources']+[f'{v} {k}' for k,v in kinds.items()]))

    st.subheader('Snapshot')
    st.markdown(sections.get('Snapshot','No snapshot returned.'))

    st.subheader('Detailed Product Insights')
    product_names={'Performance','Physical Product & Ergonomics','Controls & UI','Attachments & Mechanisms','Sensory Experience','Learning & Usability','Actual Usage Behaviours','User & Hair Context'}
    secondary_names={'Purchase & Proposition','Ownership & Customer Journey','Brand & Communication','Cross-functional Opportunities'}
    for name,desc in SECTIONS:
        if name in product_names:
            body=sections.get(name,'Insufficient evidence in the collected sources.')
            with st.expander(name, expanded=False):
                st.caption(desc); st.markdown(body)
                ids=cited_ids(body)
                if ids:
                    st.markdown('**Supporting sources**')
                    for s in sources:
                        if s['id'] in ids: st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
    st.subheader('Wider Experience & Commercial Signals')
    st.caption('Secondary layer: useful signals beyond the core product experience, shown only where the collected evidence supports them.')
    for name,desc in SECTIONS:
        if name in secondary_names:
            body=sections.get(name,'Insufficient evidence in the collected sources.')
            with st.expander(name, expanded=False):
                st.caption(desc); st.markdown(body)
                ids=cited_ids(body)
                if ids:
                    st.markdown('**Supporting sources**')
                    for s in sources:
                        if s['id'] in ids: st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")


    st.subheader('Evidence')
    with st.expander('About this evidence', expanded=False):
        independent=[s for s in sources if s['kind'] not in {'Brand content','Brand video'}]
        brand=[s for s in sources if s['kind'] in {'Brand content','Brand video'}]
        used_ids=cited_ids(report)
        used=[s for s in sources if s['id'] in used_ids]
        used_independent=[s for s in used if s['kind'] not in {'Brand content','Brand video'}]
        st.markdown(f"**Collected:** {len(sources)} sources · **Cited in report:** {len(used)} · **Independent cited sources:** {len(used_independent)} · **Brand-owned collected:** {len(brand)}")
        type_counts={}
        for x in sources: type_counts[x['kind']]=type_counts.get(x['kind'],0)+1
        st.markdown('**Source mix:** ' + ' · '.join(f"{k}: {v}" for k,v in type_counts.items()))
        st.caption('Evidence strength in findings is directional. It reflects independent source support and consistency, not consumer prevalence or a representative sample.')
        if len(used_independent) < 2:
            st.warning('Evidence base is thin: fewer than two independent sources are cited in the report. Treat findings as exploratory.')

    with st.expander('Complete source library', expanded=False):
        for s in sources: st.markdown(f"**{s['id']} · {s['kind']}** — [{s['title']}]({s['url']})")
    st.caption('Directional secondary research, not a representative prevalence estimate. Development questions require validation through user research.')
