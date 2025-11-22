import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from typing import List
from config import config

DS_PATH = config.DATASET_PATH

class ITEventSemanticSearch:
    def __init__(self, csv_path: str):
        self.df = pd.read_csv(csv_path, sep=',', encoding='utf-8')
        
        text_columns = ['Event Name', 'Description', 'Category', 'Location']
        for col in text_columns:
            if col in self.df.columns:
                self.df[col] = self.df[col].fillna('').astype(str)
        
        self.df['search_text'] = (
            self.df['Event Name'] + ". " +
            self.df['Description'] + ". " +
            self.df.get('Category', '') + ". " +
            self.df.get('Location', '')
        )
        
        self.model = SentenceTransformer('cointegrated/rubert-tiny2')
        
        self._build_vector_index()
    
    def _build_vector_index(self):
        texts = self.df['search_text'].tolist()
        embeddings = self.model.encode(texts, batch_size=32, show_progress_bar=False)
        
        embeddings = embeddings.astype(np.float32)
        faiss.normalize_L2(embeddings)
        
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings)
    
    def search(self, query: str, top_k: int = 5) -> List[str]:
        if not isinstance(query, str) or len(query.strip()) < 2:
            return []
        
        query = query.strip()
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        query_embedding = query_embedding.astype(np.float32)
        faiss.normalize_L2(query_embedding)
        
        distances, indices = self.index.search(query_embedding, top_k)
        
        results = []
        seen_events = set()
        for idx in indices[0]:
            if 0 <= idx < len(self.df):
                event_name = self.df.iloc[idx]['End Date']
                if event_name and event_name not in seen_events:
                    seen_events.add(event_name)
                    results.append(event_name)
                    if len(results) >= top_k:
                        break

        return results[:top_k]

def run_RAG(QUERY):
    answer = ITEventSemanticSearch(DS_PATH).search(QUERY)
    return answer
