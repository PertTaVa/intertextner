"""
Модуль нормализации именованных сущностей для русского, финского и шведского языков.
Используется для группировки разных падежных форм одной сущности.
"""

import re
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple

# Попытка импорта библиотек с graceful fallback
try:
    import pymorphy2
    PYTMORPHY_AVAILABLE = True
except ImportError:
    PYTMORPHY_AVAILABLE = False
    print("Предупреждение: pymorphy2 не установлен. Русская нормализация недоступна.")

try:
    from stanza import Pipeline
    STANZA_AVAILABLE = True
except ImportError:
    STANZA_AVAILABLE = False
    print("Предупреждение: stanza не установлена. Финская/шведская нормализация недоступна.")


class EntityNormalizer:
    """
    Класс для приведения именованных сущностей к нормальной форме.
    Поддерживает русский (pymorphy2), финский и шведский (stanza).
    """
    
    def __init__(self):
        # Инициализируем анализаторы только при необходимости и наличии
        self.morph_ru = None
        self.nlp_fi = None
        self.nlp_sv = None
        
        if PYTMORPHY_AVAILABLE:
            try:
                self.morph_ru = pymorphy2.MorphAnalyzer()
                print("✓ pymorphy2 загружен для русского языка")
            except Exception as e:
                print(f"! Ошибка загрузки pymorphy2: {e}")
        
        # Stanza будем загружать лениво (при первом запросе)
        self._stanza_loaded = {'fi': False, 'sv': False}
    
    def _get_stanza_pipeline(self, lang: str) -> Optional[Pipeline]:
        """Ленивая загрузка Stanza для языка"""
        if not STANZA_AVAILABLE:
            return None
        
        if lang == 'fi' and not self._stanza_loaded['fi']:
            try:
                self.nlp_fi = Pipeline('fi', processors='lemma', use_gpu=False, verbose=False)
                self._stanza_loaded['fi'] = True
                print("✓ Stanza (финский) загружена")
            except Exception as e:
                print(f"! Ошибка загрузки Stanza для финского: {e}")
                return None
        
        elif lang == 'sv' and not self._stanza_loaded['sv']:
            try:
                self.nlp_sv = Pipeline('sv', processors='lemma', use_gpu=False, verbose=False)
                self._stanza_loaded['sv'] = True
                print("✓ Stanza (шведский) загружена")
            except Exception as e:
                print(f"! Ошибка загрузки Stanza для шведского: {e}")
                return None
        
        return self.nlp_fi if lang == 'fi' else self.nlp_sv if lang == 'sv' else None
    
    def normalize_russian(self, text: str, entity_type: str = None) -> str:
        """Нормализация русских сущностей через pymorphy2"""
        if not self.morph_ru:
            return text
        
        # Очищаем от лишних символов
        text = re.sub(r'[^\w\s-]', '', text).strip()
        if not text:
            return text
        
        try:
            parsed = self.morph_ru.parse(text)[0]
            normal_form = parsed.normal_form
            
            # Для локаций можно сохранять оригинальный регистр первой буквы
            if entity_type == 'LOC' and text and text[0].isupper():
                normal_form = normal_form.capitalize()
            
            return normal_form
        except Exception:
            return text
    
    def normalize_scandinavian(self, text: str, lang: str) -> str:
        """Нормализация финских/шведских сущностей через Stanza"""
        nlp = self._get_stanza_pipeline(lang)
        if not nlp:
            return text
        
        try:
            doc = nlp(text)
            if doc.sentences and doc.sentences[0].words:
                return doc.sentences[0].words[0].lemma
        except Exception:
            pass
        return text
    
    def normalize(self, text: str, lang: str = 'ru', entity_type: str = None) -> str:
        """
        Основной метод нормализации.
        
        Args:
            text: Исходный текст сущности
            lang: Язык ('ru', 'fi', 'sv')
            entity_type: Тип сущности (PER, LOC и т.д.) для доп. логики
        
        Returns:
            Нормализованная форма
        """
        if not text:
            return ""
        
        if lang == 'ru':
            return self.normalize_russian(text, entity_type)
        elif lang in ('fi', 'sv'):
            return self.normalize_scandinavian(text, lang)
        else:
            return text


class EntityGrouper:
    """
    Группирует сущности по нормальной форме и собирает статистику.
    """
    
    def __init__(self, normalizer: EntityNormalizer = None):
        self.normalizer = normalizer or EntityNormalizer()
    
    def group_entities(self, 
                      entities: List[Dict[str, Any]], 
                      lang: str = 'ru') -> Dict[str, Dict[str, Any]]:
        """
        Группирует список сущностей по нормальной форме.
        
        Args:
            entities: Список сущностей [{'text': '...', 'type': '...', 'context': '...'}, ...]
            lang: Язык текста
        
        Returns:
            Словарь сгруппированных сущностей:
            {
                'норм_форма': {
                    'count': int,
                    'type': str,
                    'variants': list,
                    'contexts': list,
                    'original_texts': list
                }
            }
        """
        grouped = defaultdict(lambda: {
            'count': 0,
            'type': None,
            'variants': set(),
            'contexts': [],
            'original_texts': []
        })
        
        for ent in entities:
            text = ent.get('text', '')
            ent_type = ent.get('type', 'MISC')
            context = ent.get('context', '')
            
            if not text:
                continue
            
            # Нормализуем
            norm = self.normalizer.normalize(text, lang, ent_type)
            
            # Обновляем статистику
            grouped[norm]['count'] += 1
            grouped[norm]['variants'].add(text)
            grouped[norm]['original_texts'].append(text)
            if context and len(grouped[norm]['contexts']) < 5:  # храним до 5 контекстов
                grouped[norm]['contexts'].append(context)
            
            # Сохраняем тип (берем наиболее частый или первый)
            if not grouped[norm]['type']:
                grouped[norm]['type'] = ent_type
        
        # Преобразуем set в list для JSON
        result = {}
        for norm, data in grouped.items():
            result[norm] = {
                'count': data['count'],
                'type': data['type'],
                'variants': list(data['variants']),
                'contexts': data['contexts']
            }
        
        return result
    
    def find_intersections(self, 
                          entities1: List[Dict[str, Any]], 
                          entities2: List[Dict[str, Any]],
                          lang1: str = 'ru',
                          lang2: str = 'ru') -> Dict[str, Dict[str, Any]]:
        """
        Находит общие сущности в двух списках после нормализации.
        
        Returns:
            Словарь общих сущностей с информацией из обоих текстов
        """
        grouped1 = self.group_entities(entities1, lang1)
        grouped2 = self.group_entities(entities2, lang2)
        
        intersections = {}
        all_norms = set(grouped1.keys()) | set(grouped2.keys())
        
        for norm in all_norms:
            data1 = grouped1.get(norm)
            data2 = grouped2.get(norm)
            
            if data1 and data2:  # сущность есть в обоих текстах
                intersections[norm] = {
                    'type': data1['type'],  # или data2['type']
                    'in_source': {
                        'count': data1['count'],
                        'variants': data1['variants'],
                        'contexts': data1['contexts']
                    },
                    'in_comparison': {
                        'count': data2['count'],
                        'variants': data2['variants'],
                        'contexts': data2['contexts']
                    },
                    'total_count': data1['count'] + data2['count']
                }
        
        return intersections
    
    def prepare_for_viz(self, 
                       intersections: Dict[str, Dict[str, Any]], 
                       source_name: str = "Source",
                       comp_name: str = "Comparison") -> Dict[str, Any]:
        """
        Подготавливает данные для визуализации в D3.js (формат nodes/links).
        """
        nodes = []
        links = []
        
        # Цвета для типов сущностей
        colors = {
            'PER': '#ff7f7f',  # красноватый
            'LOC': '#7fbfff',  # голубой
            'ORG': '#bfff7f',  # зеленоватый
            'DATE': '#ffbf7f',  # оранжевый
            'MISC': '#d3d3d3'   # серый
        }
        
        # Добавляем узлы для текстов
        nodes.append({
            'id': source_name,
            'type': 'text',
            'color': '#cccccc',
            'size': 10
        })
        
        nodes.append({
            'id': comp_name,
            'type': 'text',
            'color': '#cccccc',
            'size': 10
        })
        
        # Добавляем узлы для общих сущностей
        for norm, data in intersections.items():
            ent_type = data.get('type', 'MISC')
            nodes.append({
                'id': norm,
                'type': ent_type,
                'color': colors.get(ent_type, '#d3d3d3'),
                'size': 5 + min(data['total_count'], 10),  # размер зависит от частоты
                'frequency': data['total_count'],
                'contexts_source': data['in_source']['contexts'],
                'contexts_comp': data['in_comparison']['contexts'],
                'variants_source': data['in_source']['variants'],
                'variants_comp': data['in_comparison']['variants']
            })
            
            # Связи с исходными текстами
            links.append({
                'source': source_name,
                'target': norm,
                'value': data['in_source']['count']
            })
            
            links.append({
                'source': comp_name,
                'target': norm,
                'value': data['in_comparison']['count']
            })
        
        return {
            'nodes': nodes,
            'links': links
        }