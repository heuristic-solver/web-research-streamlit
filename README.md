# Goal

This project builds a web research assistant that answers questions by searching the internet, evaluating sources, and generating summaries with proper citations. The agent aims to provide accurate information while being transparent about its sources and avoiding hallucinations.

# Tech Stack

    Frontend: Streamlit for the web interface

    Search: SERP API for web search results

    AI: Google's Gemini 1.5 Flash for content summarization

    Web Scraping: BeautifulSoup for content extraction

    Language: Python 3.8+

# How to Run

    Install dependencies:
    

    pip install streamlit requests beautifulsoup4 google-generativeai

Get API keys:

Sign up for SERP API at serpapi.com
Get a Gemini API key from Google AI Studio

Set up secrets:
Create .streamlit/secrets.toml with:

    SERP_API_KEY="Your api key here"
    GEMINI_API_KEY="Your api key here"
    

Run the app:
    

    streamlit run web_research_agent.py
