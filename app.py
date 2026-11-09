from pathlib import Path
import re
import pandas as pd
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title='GPU Alternative Finder',page_icon='🔎',layout='wide')
st.title('🔎 GPU Alternative Finder AI')
st.caption('검색창에 제품명 입력 → 일치 모델 확인 → 대체상품 자동 추천 · 별도 파일 업로드 불필요')
df=pd.read_csv(Path(__file__).with_name('catalog.csv'),encoding='utf-8-sig').fillna('')
for c in ['vram_gb','length_mm','tdp_w','stock','buy_price','sell_price']:
    df[c]=pd.to_numeric(df[c],errors='coerce')

def normalize(s):
    s=str(s).casefold().replace('지포스','').replace('geforce','')
    return re.sub(r'[^a-z0-9가-힣]+',' ',s).strip()

def search_catalog(query):
    words=normalize(query).split()
    if not words:return df.iloc[0:0].copy()
    return df[df['model'].apply(lambda s:all(w in normalize(s) for w in words))].copy()

with st.form('search_form'):
    q=st.text_input('GPU 모델명 검색',placeholder='예: ZOTAC RTX 5080 SOLID CORE / MSI RTX 5070 Ti')
    submitted=st.form_submit_button('🔎 대체상품 검색',type='primary',use_container_width=True)
if submitted:st.session_state['last_query']=q.strip()
query=st.session_state.get('last_query','')
if not query:
    st.info('위 검색창에 제품명을 입력한 뒤 검색 버튼을 누르세요. 예: RTX 5080 SOLID CORE')
    st.stop()

matches=search_catalog(query)
st.subheader('검색 결과')
st.caption(f'등록 제품 {len(df)}개 중 검색 결과 {len(matches)}개 · 전체 RTX 50 제품 목록이 아닌 부분 카탈로그')
if not matches.empty:
    st.dataframe(matches[['brand','model','chipset','vram_gb','length_mm','danawa_url']],hide_index=True,use_container_width=True)
    # No dropdown: automatically select strongest matching product using token overlap and specificity
    ranked=matches.assign(_score=matches['model'].apply(lambda s:len(set(normalize(query).split()) & set(normalize(s).split()))))
    base=ranked.sort_values(['_score','model'],ascending=[False,True]).iloc[0]
    st.success(f'추천 기준 제품: {base["model"]}')
    if len(matches)>1:st.caption('여러 모델이 검색되었습니다. 가장 잘 일치하는 첫 제품을 기준으로 추천합니다. 정확한 모델명을 입력하면 결과가 더 정확해집니다.')
    c1,c2,c3=st.columns(3)
    with c1:max_length=st.number_input('최대 길이(mm, 0=제한 없음)',min_value=0,value=0)
    with c2:min_vram=st.number_input('최소 VRAM(GB)',min_value=0,value=int(base.vram_gb) if pd.notna(base.vram_gb) else 0)
    with c3:qty=st.number_input('필요 수량',min_value=1,value=1)
    candidates=df[(df['sku']!=base['sku']) & (df['chipset']==base['chipset']) & (df['vram_gb']>=min_vram)].copy()
    if max_length:candidates=candidates[candidates['length_mm'].notna() & (candidates['length_mm']<=max_length)]
    candidates['재고 확인']=candidates['stock'].apply(lambda x:'미확인' if pd.isna(x) else ('수량 충족' if x>=qty else '수량 부족'))
    candidates['판매가 확인']=candidates['sell_price'].apply(lambda x:'미확인' if pd.isna(x) else f'{x:,.0f}원')
    candidates['_rank']=candidates['stock'].apply(lambda x:0 if pd.notna(x) and x>=qty else (2 if pd.notna(x) else 1))
    candidates=candidates.sort_values(['_rank','length_mm','model'],na_position='last').head(10)
    st.subheader('동일 칩셋 대체상품 추천')
    st.caption('동일 칩셋·VRAM 기준 후보입니다. 재고/가격이 미확인인 상품은 공급 가능 확정이 아닙니다.')
    if candidates.empty:st.warning('현재 카탈로그에서 조건에 맞는 대체상품이 없습니다. 아래 웹 검색을 이용하세요.')
    else:
        st.dataframe(candidates[['model','chipset','vram_gb','length_mm','tdp_w','재고 확인','판매가 확인','danawa_url']],hide_index=True,use_container_width=True)
        st.download_button('대체 후보 CSV 저장',candidates.drop(columns=['_rank']).to_csv(index=False).encode('utf-8-sig'),'gpu_alternatives.csv','text/csv')
else:
    st.warning('등록 카탈로그에서 일치하는 제품을 찾지 못했습니다. 검색어를 줄이거나 아래 웹 검색을 이용하세요.')

st.divider()
st.subheader('🌐 최신 웹 검색 (선택)')
st.caption('컴퓨존·다나와·조이젠·아이코다·이지가이드 및 제조사 공식 사이트에서 최신 공개정보를 검색합니다. API 키와 이용요금이 필요합니다.')
with st.expander('OpenAI API 설정'):
    key=st.text_input('API 키',type='password')
    model=st.text_input('웹 검색 지원 모델',value='gpt-4.1-mini')
if st.button('인터넷에서 대체상품 찾기',use_container_width=True):
    if not key:st.error('OpenAI API 설정에서 API 키를 입력해 주세요.')
    else:
        prompt=(f'한국 B2B VGA MD용 GPU 대체상품을 최신 웹 검색으로 조사하세요. 요청 제품: {query}. '
                '동일 GPU 칩셋과 VRAM 우선, 대체 모델 3~5개. 공식 제조사 사양을 교차 확인하고 '
                '컴퓨존, 다나와, 조이젠, 아이코다, 이지가이드의 공개 판매가격과 상품 URL을 우선 조사하세요. '
                '제품별 정확한 모델명, 칩셋, VRAM, 길이, 보조전원, 가격, 확인 날짜, 링크, 추천 사유를 표로 정리하세요. '
                '확인되지 않은 가격/재고/사양은 미확인으로 표기하고 링크나 수치를 만들어내지 마세요. '
                '공개 쇼핑몰 판매 상태를 공급사 실재고로 간주하지 마세요. 마지막에 CAM 안내문을 작성하세요.')
        try:
            with st.spinner('웹에서 확인 중...'):
                r=OpenAI(api_key=key,timeout=120).responses.create(model=model,tools=[{'type':'web_search_preview'}],input=prompt,max_output_tokens=3500)
            if r.output_text:
                st.markdown(r.output_text)
                st.download_button('웹 검색 보고서 저장',r.output_text,'gpu_web_report.md','text/markdown')
            else:st.warning('검색 결과가 비어 있습니다.')
        except Exception as e:st.error(f'웹 검색 오류: {e}')
st.caption('주의: 기본 CSV는 53개 부분 목록이며 가격·재고 공란은 미확인입니다. 공개 정보와 실제 납품 가능 여부는 다를 수 있습니다.')
