import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import time
import re
from urllib.parse import urlparse
import logging
from datetime import datetime
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebResearchAgent")

SERP_API_KEY = st.secrets.get("SERP_API_KEY", "your-serp-api-key-here")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "your-gemini-api-key-here")

TOP_N = 5
TOP_SOURCES = 3

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

class WebResearchAgent:
    def __init__(self):
        self.search_history = []
        self.response_history = []
        
    def search_web(self, query, num_results=TOP_N):
        try:
            url = "https://serpapi.com/search"
            params = {
                'q': query,
                'api_key': SERP_API_KEY,
                'engine': 'google',
                'num': num_results,
                'hl': 'en',
                'gl': 'us'
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            search_results = response.json()
            
            results = []
            if 'organic_results' in search_results:
                for item in search_results['organic_results']:
                    results.append({
                        'title': item.get('title', 'No title'),
                        'link': item.get('link', ''),
                        'snippet': item.get('snippet', 'No snippet available')
                    })
            
            self.search_history.append({
                'query': query,
                'timestamp': datetime.now().isoformat(),
                'results_count': len(results),
                'results': results
            })
            
            return results
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def fetch_page_content(self, url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for script in soup(["script", "style"]):
                script.decompose()
            
            text = soup.get_text()
            
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text[:5000]
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def score_source_quality(self, url, content):
        score = 5
        
        domain = urlparse(url).netloc.lower()
        
        reputable_domains = ['.edu', '.gov', '.org', 'wikipedia.org', 'bbc.com', 'reuters.com', 
                            'nytimes.com', 'nature.com', 'sciencedirect.com', 'springer.com']
        if any(rep_domain in domain for rep_domain in reputable_domains):
            score += 2
        
        questionable_domains = ['blogspot.com', 'wordpress.com', 'medium.com', 'quora.com']
        if any(q_domain in domain for q_domain in questionable_domains):
            score -= 1
        
        if content:
            content_length = len(content)
            if content_length > 2000:
                score += 1
            elif content_length < 500:
                score -= 1
            
            academic_indicators = ['study', 'research', 'data', 'analysis', 'experiment', 'results']
            if any(indicator in content.lower() for indicator in academic_indicators):
                score += 1
        
        return max(1, min(10, score))
    
    def remove_duplicate_sources(self, sources):
        unique_sources = []
        seen_domains = set()
        
        for source in sources:
            domain = urlparse(source['link']).netloc
            if domain not in seen_domains:
                unique_sources.append(source)
                seen_domains.add(domain)
        
        return unique_sources
    
    def generate_answer(self, query, sources):
        if not sources:
            return "I don't know", []
        
        context = ""
        for i, source in enumerate(sources):
            context += f"SOURCE {i+1}:\nURL: {source['link']}\nCONTENT: {source['content'][:1000]}\n\n"
        
        prompt = f"""
        You are a research assistant. Based on the following sources, provide a concise answer to the query.
        If the information is not available in the sources, say "I don't know".
        Always cite your sources using numbers like [1], [2], etc.
        
        Query: {query}
        
        Sources:
        {context}
        
        Answer:
        """
        
        try:
            response = model.generate_content(prompt)
            answer = response.text
            
            citations = []
            citation_pattern = r'\[(\d+)\]'
            cited_indices = set(re.findall(citation_pattern, answer))
            
            for idx in cited_indices:
                idx = int(idx) - 1
                if 0 <= idx < len(sources):
                    citations.append(sources[idx])
            
            return answer, citations
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return "I encountered an error while generating the answer. Please try again.", []
    
    def process_query(self, query):
        start_time = time.time()
        
        metrics = {
            'processing_time': 0,
            'sources_evaluated': 0,
            'sources_used': 0
        }
        
        try:
            st.info("Searching the web...")
            search_results = self.search_web(query)
            
            if not search_results:
                return "I couldn't find any relevant sources for your query. Please try a different search term.", [], metrics
            
            st.info("Analyzing sources...")
            sources_with_content = []
            for result in search_results:
                content = self.fetch_page_content(result['link'])
                if content:
                    quality_score = self.score_source_quality(result['link'], content)
                    sources_with_content.append({
                        'title': result['title'],
                        'link': result['link'],
                        'snippet': result['snippet'],
                        'content': content,
                        'quality_score': quality_score
                    })
            
            unique_sources = self.remove_duplicate_sources(sources_with_content)
            sorted_sources = sorted(unique_sources, key=lambda x: x['quality_score'], reverse=True)
            top_sources = sorted_sources[:TOP_SOURCES]
            
            st.info("Generating answer...")
            answer, citations = self.generate_answer(query, top_sources)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            metrics = {
                'processing_time': processing_time,
                'sources_evaluated': len(sources_with_content),
                'sources_used': len(citations)
            }
            
            self.response_history.append({
                'query': query,
                'timestamp': datetime.now().isoformat(),
                'answer': answer,
                'sources_used': [s['link'] for s in citations],
                'processing_time': processing_time
            })
            
            return answer, citations, metrics
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            end_time = time.time()
            metrics['processing_time'] = end_time - start_time
            return f"An error occurred while processing your query: {str(e)}", [], metrics

if 'agent' not in st.session_state:
    st.session_state.agent = WebResearchAgent()

st.set_page_config(page_title="Web Research Agent", layout="wide")
st.title("Web Research Agent")
st.markdown("Ask a question and I'll search the web to find answers from reliable sources.")

with st.sidebar:
    st.header("Settings")
    st.info("This agent uses SERP API and Gemini to answer questions with proper citations.")
    
    st.header("Sample Queries")
    sample_queries = [
        "What are the latest developments in quantum computing?",
        "How does climate change affect biodiversity?",
        "What are the health benefits of intermittent fasting?",
        "Explain the concept of blockchain technology",
        "What are the main causes of the 2008 financial crisis?"
    ]
    
    for query in sample_queries:
        if st.button(query, key=query):
            st.session_state.query_input = query
    
    st.header("Health Check")
    if st.button("Run Test Queries"):
        test_queries = [
            "What is the capital of France?",
            "Who developed the theory of relativity?",
            "What is the chemical symbol for gold?"
        ]
        
        results = []
        for tq in test_queries:
            with st.spinner(f"Testing: {tq}"):
                answer, citations, metrics = st.session_state.agent.process_query(tq)
                results.append({
                    'query': tq,
                    'answer': answer,
                    'sources_used': len(citations),
                    'time': metrics.get('processing_time', 0)
                })
        
        st.success("Test completed!")
        for res in results:
            st.write(f"Q: {res['query']}")
            st.write(f"A: {res['answer'][:100]}...")
            st.write(f"Sources: {res['sources_used']}, Time: {res['time']:.2f}s")
            st.divider()

query = st.text_input("Enter your question:", key="query_input", placeholder="e.g., What are the benefits of renewable energy?")

if st.button("Research") and query:
    with st.spinner("Researching your question..."):
        answer, citations, metrics = st.session_state.agent.process_query(query)
    
    st.subheader("Answer")
    st.write(answer)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Processing Time", f"{metrics.get('processing_time', 0):.2f}s")
    col2.metric("Sources Evaluated", metrics.get('sources_evaluated', 0))
    col3.metric("Sources Used", metrics.get('sources_used', 0))
    
    if citations:
        st.subheader("Sources")
        for i, source in enumerate(citations):
            with st.expander(f"{i+1}. {source.get('title', 'No title')} (Quality: {source.get('quality_score', 'N/A')}/10)"):
                st.write(f"URL: {source.get('link', 'No URL')}")
                st.write(f"Snippet: {source.get('snippet', 'No snippet available')}")
                st.write(f"Why this source was trusted: This source from {urlparse(source.get('link', '')).netloc} has a quality score of {source.get('quality_score', 'N/A')}/10 based on domain reputation and content quality.")
    else:
        st.warning("No sources were used in generating this answer.")
    
    with st.expander("Debug Information"):
        st.json({
            "query": query,
            "processing_time": metrics.get('processing_time', 0),
            "sources_evaluated": metrics.get('sources_evaluated', 0),
            "sources_used": [s.get('link', '') for s in citations] if citations else []
        })

with st.expander("View Query History"):
    if st.session_state.agent.response_history:
        for i, response in enumerate(reversed(st.session_state.agent.response_history)):
            st.write(f"Query {i+1}: {response.get('query', 'No query')}")
            st.write(f"Time: {response.get('timestamp', 'No timestamp')}")
            st.write(f"Processing Time: {response.get('processing_time', 0):.2f}s")
            st.write(f"Sources Used: {len(response.get('sources_used', []))}")
            st.divider()
    else:
        st.info("No query history yet.")

st.markdown("---")
st.markdown("How it works:")
st.markdown("1. Enter your question in the search box")
st.markdown("2. The agent searches the web using SERP API")
st.markdown("3. Content is extracted from top results and scored for quality")
st.markdown("4. Gemini Flash analyzes the content and generates a summary with citations")
st.markdown("5. You get an answer with links to the original sources")