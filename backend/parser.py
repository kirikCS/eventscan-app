import hashlib
import re
import time
import json
import os
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse, unquote
import requests
from bs4 import BeautifulSoup
import logging
from gemma_inference import GET_LLM_ANSWER

logger = logging.getLogger(__name__)

class DuckDuckGoSearch:
    def __init__(self, cache_size: int = 200, cache_ttl: int = 1800):
        self.cache: OrderedDict = OrderedDict()
        self.cache_ttl = cache_ttl
        self.cache_timestamps: Dict[str, datetime] = {}
        self.cache_size = cache_size
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://duckduckgo.com/',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def _generate_cache_key(self, query: str) -> str:
        salt = "ddg_v2"
        normalized = re.sub(r'\s+', ' ', query.lower().strip())
        return hashlib.sha256(f"{normalized}{salt}".encode('utf-8')).hexdigest()
    
    def _is_ru_domain(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            allowed = ['.ru', '.su', '.рф', '.moscow', '.tech', '.com', '.org', '.net']
            return any(domain.endswith(tld) or f".{tld}" in domain for tld in allowed)
        except:
            return False

    def _clean_url(self, raw_url: str) -> Optional[str]:
        try:
            if 'duckduckgo.com/l/?uddg=' in raw_url:
                match = re.search(r'uddg=([^&]+)', raw_url)
                if match:
                    raw_url = unquote(match.group(1))
            
            raw_url = raw_url.strip()
            if not raw_url.startswith(('http://', 'https://')):
                return None
                
            parsed = urlparse(raw_url)
            if not parsed.netloc:
                return None
                
            if 'duckduckgo' in parsed.netloc or 'yandex' in parsed.netloc or 'google' in parsed.netloc or 'vk' in parsed.netloc:
                return None
                
            return raw_url
        except:
            return None
    
    def search(self, query: str) -> List[str]:
        cache_key = self._generate_cache_key(query)
        if cache_key in self.cache and (datetime.now() - self.cache_timestamps.get(cache_key, datetime.min)).total_seconds() < self.cache_ttl:
            return self.cache[cache_key]

        logger.info(f"DDG QUERY: {query}...")
        url = "https://html.duckduckgo.com/html/"
        data = {'q': query, 'kl': 'ru-ru', 'df': 'y'}

        try:
            resp = self.session.post(url, data=data, timeout=15)
            resp.raise_for_status()
            
            urls = []
            seen = set()
            soup = BeautifulSoup(resp.text, 'html.parser')
            links = soup.find_all('a', class_='result__a')
            
            for link_tag in links:
                href = link_tag.get('href')
                if not href: continue
                
                clean = self._clean_url(href)
                if clean and clean not in seen:
                    if self._is_ru_domain(clean):
                        urls.append(clean)
                        seen.add(clean)
            
            if not urls:
                raw_links = re.findall(r'href=["\'](https?://[^"\']+)["\']', resp.text)
                for href in raw_links:
                    clean = self._clean_url(href)
                    if clean and clean not in seen and self._is_ru_domain(clean):
                        urls.append(clean)
                        seen.add(clean)

            self.cache[cache_key] = urls[:10]
            self.cache_timestamps[cache_key] = datetime.now()
            return urls[:10]

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

class EventParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; EventBot/1.0)',
            'Accept-Language': 'ru-RU,ru;q=0.9',
        })

        self.date_patterns = [
            r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})',
            r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})',
            r'(\d{1,2})\s+([а-яА-Я]+)\s+(\d{4})',
            r'(\d{1,2})\s+([а-яА-Я]+)'
        ]
        self.months = {
            'янв': 1, 'января': 1, 'январь': 1,
            'фев': 2, 'февраля': 2, 'февраль': 2,
            'мар': 3, 'марта': 3, 'март': 3,
            'апр': 4, 'апреля': 4, 'апрель': 4,
            'мая': 5, 'май': 5,
            'июн': 6, 'июня': 6, 'июнь': 6,
            'июл': 7, 'июля': 7, 'июль': 7,
            'авг': 8, 'августа': 8, 'август': 8,
            'сен': 9, 'сентября': 9, 'сентябрь': 9,
            'окт': 10, 'октября': 10, 'октябрь': 10,
            'ноя': 11, 'ноября': 11, 'ноябрь': 11,
            'дек': 12, 'декабря': 12, 'декабрь': 12,
        }
    
    def get_soup(self, url: str) -> Optional[BeautifulSoup]:
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            if response.encoding is None:
                response.encoding = 'utf-8'
            return BeautifulSoup(response.text, 'html.parser')
        except Exception:
            return None

    def _get_meta(self, soup: BeautifulSoup, attrs_list: List[Dict]) -> str:
        for attrs in attrs_list:
            tag = soup.find('meta', attrs=attrs)
            if tag and tag.get('content'):
                return tag['content'].strip()
        return ""

    def _is_valid_title(self, title: str) -> bool:
        if not title or len(title) < 5:
            return False
        
        has_cyrillic = bool(re.search('[а-яА-ЯёЁ]', title))
        has_latin = bool(re.search('[a-zA-Z]', title))
        has_garbage = bool(re.search(r'[ÐÑÐ]{3,}', title)) # and not has_garbage
        
        return (has_cyrillic or has_latin) and not has_garbage

    def _extract_relevant_content(self, soup: BeautifulSoup, max_length: int = 1500) -> str:
        for element in soup(["script", "style", "header", "footer", "nav"]):
            element.decompose()
        
        main_content = soup.find('main') or soup.find(id='content') or soup.find(class_=re.compile(r'(content|main|article)'))
        if main_content:
            text = main_content.get_text(" ", strip=True)
        else:
            text = soup.get_text(" ", strip=True)
        
        text = re.sub(r'\s+', ' ', text)
        return text[:max_length] + "..." if len(text) > max_length else text

    def _parse_llm_response(self, response: str) -> dict:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
        
        logger.warning(f"Failed to parse LLM response: {response[:100]}...")
        return {}
    
    def _parse_date_string(self, date_str: str, current_year: int = None) -> Optional[datetime]:
        if not date_str or not isinstance(date_str, str):
            return None
        
        if current_year is None:
            current_year = datetime.now().year
        
        for pattern in self.date_patterns:
            match = re.search(pattern, date_str)
            if not match:
                continue
            
            groups = match.groups()
            try:
                if len(groups) == 3:
                    if pattern.startswith(r'(\d{4})'):
                        year, month, day = map(int, groups)
                    else:
                        day, month, year = map(int, groups)
                    return datetime(year, month, day)
                
                elif len(groups) == 2:
                    day = int(groups[0])
                    month_str = groups[1].lower()
                    
                    for key, month_num in self.months.items():
                        if key in month_str:
                            return datetime(current_year, month_num, day)
            except (ValueError, TypeError):
                continue
        
        try:
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            pass
        
        logger.warning(f"Could not parse date string: '{date_str}'")
        return None

    def parse(self, url: str) -> Dict[str, Any]:
        soup = self.get_soup(url)
        data = {k: '' for k in ['Year', 'Start Date', 'End Date', 'Event Name', 'Event Type', 
                                'Description', 'Participants Count', 'Speakers/Organizers', 
                                'Partners', 'Category', 'Location', 'Source URL', 'Parsed Date']}
        data['Source URL'] = url
        
        if not soup:
            return data

        title = self._get_meta(soup, [
            {'property': 'og:title'}, {'name': 'twitter:title'}, {'name': 'title'}
        ])
        if not title and soup.title:
            title = soup.title.string or ''
        
        if not self._is_valid_title(title):
            logger.warning(f"Skipped invalid title: {title[:50]}...")
            return data

        description = self._get_meta(soup, [
            {'property': 'og:description'}, {'name': 'description'}
        ])
        content = self._extract_relevant_content(soup, max_length=1500)
        
        current_year = datetime.now().year
        prompt = f"""
Ты — эксперт по анализу мероприятий. Проанализируй текст мероприятия и верни ТОЛЬКО JSON со следующими полями:
- "Event Name": Название мероприятия (строка)
- "Event Type": Тип мероприятия (строго один из: "Конференция", "Митап", "Хакатон", "Вебинар", "Выставка", "Фестиваль", "Мероприятие")
- "Description": Краткое описание (максимум 250 символов)
- "Start Date": Дата начала в формате "DD.MM.YYYY". ПРИМЕРЫ: "25.12.2024", "01.01.2025". Если год не указан, используй {current_year}
- "End Date": Дата окончания в формате "DD.MM.YYYY". Если мероприятие однодневное, дублируй Start Date
- "Year": Год проведения (например, "{current_year}")
- "Location": Место проведения (город или "Онлайн")
- "Speakers/Organizers": Ключевые спикеры или организаторы (максимум 100 символов)
- "Partners": Партнеры и спонсоры (максимум 100 символов)
- "Participants Count": Ожидаемое/фактическое количество участников (например, "200+")
- "Category": Основные категории (например, "IT, Образование")

Контекст:
Название: {title}
Описание: {description}
Содержимое: {content}

ВАЖНО:
1. Верни ТОЛЬКО JSON без дополнительного текста
2. Для дат ИСПОЛЬЗУЙ СТРОГО ФОРМАТ "DD.MM.YYYY"
3. Если поле неизвестно, оставь его пустым
4. Никогда не используй формат "YYYY-MM-DD" для дат
"""
        
        try:
            logger.debug(f"Sending request to LLM for URL: {url[:50]}...")
            llm_response = GET_LLM_ANSWER(prompt.strip())
            event_details = self._parse_llm_response(llm_response)
            
            field_mapping = {
                "Event Name": "Event Name",
                "Event Type": "Event Type",
                "Description": "Description",
                "Start Date": "Start Date",
                "End Date": "End Date",
                "Year": "Year",
                "Location": "Location",
                "Speakers/Organizers": "Speakers/Organizers",
                "Partners": "Partners",
                "Participants Count": "Participants Count",
                "Category": "Category"
            }
            
            for llm_field, data_field in field_mapping.items():
                value = event_details.get(llm_field, "").strip()
                data[data_field] = value
            
            if data['Start Date']:
                parsed_date = self._parse_date_string(data['Start Date'], current_year)
                if parsed_date:
                    data['Parsed Date'] = parsed_date
                    data['Start Date'] = parsed_date.strftime("%d.%m.%Y")
            
            if data['End Date']:
                parsed_end = self._parse_date_string(data['End Date'], current_year)
                if parsed_end:
                    data['End Date'] = parsed_end.strftime("%d.%m.%Y")
        
        except Exception as e:
            logger.error(f"LLM processing failed for {url}: {str(e)}")
        
        return data

def parse_events(query: str) -> Tuple[Dict[str, Any], ...]:
    today = datetime.now()
    logger.info(f"Starting event parsing for query: {query}")
    
    searcher = DuckDuckGoSearch()
    urls = searcher.search(query)
    
    if not urls:
        logger.warning("No URLs found for the query")
        return tuple()

    logger.info(f"Found {len(urls)} URLs to process")
    parser = EventParser()
    events = []
    added_count = 0
    skipped_count = 0

    for i, url in enumerate(urls, 1):
        try:
            logger.debug(f"Processing URL {i}/{len(urls)}: {url}")
            event_data = parser.parse(url)
            
            if not event_data['Event Name'] or not parser._is_valid_title(event_data['Event Name']):
                logger.warning(f"Skipped invalid title for URL: {url}")
                skipped_count += 1
                continue
            
            parsed_date = event_data.get('Parsed Date')
            if parsed_date:
                if parsed_date < today:
                    logger.warning(f"Skipped past event ({parsed_date.strftime('%d.%m.%Y')}) for URL: {url}")
                    skipped_count += 1
                    continue
            
            events.append(event_data)
            added_count += 1
            logger.info(f"Added event: {event_data['Event Name'][:60]}...")
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            skipped_count += 1

    logger.info(f"Parsed events: {added_count} added, {skipped_count} skipped")
    return tuple(events)

def GET_EVENTS(query: str):
    if len(query.split(" ")) < 3:
        act_query = f"IT-мероприятия в Санкт-Петербурге для {query}"
    else:
        act_query = query
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    events = parse_events(act_query)
    return events
