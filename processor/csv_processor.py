"""
Processore CSV/Excel per inventario
Estrae dati vini da file CSV e Excel
"""
import io
import logging
import pandas as pd
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class CSVProcessor:
    """Processore CSV/Excel per inventario"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def process_file(self, file_content: bytes, file_name: str, file_type: str) -> List[Dict[str, Any]]:
        """
        Elabora un file CSV o Excel
        
        Args:
            file_content: Contenuto binario del file
            file_name: Nome del file
            file_type: Tipo file ('csv' o 'excel')
            
        Returns:
            Lista di vini estratti
        """
        try:
            self.logger.info(f"Elaborazione file {file_type}: {file_name}")
            
            # Leggi il file in base al tipo
            if file_type == 'csv':
                df = pd.read_csv(io.BytesIO(file_content), encoding='utf-8')
            elif file_type == 'excel':
                df = pd.read_excel(io.BytesIO(file_content))
            else:
                raise ValueError(f"Tipo file non supportato: {file_type}")
            
            self.logger.info(f"File letto: {len(df)} righe, {len(df.columns)} colonne")
            
            # Elabora i dati
            wines = self._process_dataframe(df)
            
            self.logger.info(f"Vini estratti: {len(wines)}")
            return wines
            
        except Exception as e:
            self.logger.error(f"Errore elaborazione file: {e}")
            return []
    
    def _process_dataframe(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Elabora il DataFrame per estrarre i vini
        
        Args:
            df: DataFrame con i dati
            
        Returns:
            Lista di vini estratti
        """
        wines = []
        
        # Normalizza i nomi delle colonne
        df.columns = df.columns.str.lower().str.strip()
        
        # Mappa delle colonne comuni
        column_mapping = self._map_columns(df.columns)
        
        for index, row in df.iterrows():
            try:
                wine_data = self._extract_wine_from_row(row, column_mapping)
                if wine_data:
                    wines.append(wine_data)
            except Exception as e:
                self.logger.error(f"Errore elaborazione riga {index}: {e}")
                continue
        
        return wines
    
    def _map_columns(self, columns: List[str]) -> Dict[str, str]:
        """
        Mappa le colonne del file alle colonne standard
        
        Args:
            columns: Lista delle colonne
            
        Returns:
            Mappatura colonne
        """
        mapping = {}
        
        # Pattern comuni per le colonne
        patterns = {
            'name': ['nome', 'name', 'etichetta', 'vino', 'wine', 'prodotto'],
            'producer': ['produttore', 'producer', 'marca', 'brand', 'casa'],
            'quantity': ['quantità', 'quantity', 'qty', 'stock', 'magazzino', 'bottiglie'],
            'vintage': ['annata', 'vintage', 'anno', 'year'],
            'wine_type': ['tipo', 'type', 'colore', 'color'],
            'region': ['regione', 'region', 'zona', 'area'],
            'price': ['prezzo', 'price', 'costo', 'cost'],
            'min_quantity': ['minimo', 'min', 'scorta_minima', 'min_stock']
        }
        
        for standard_col, patterns_list in patterns.items():
            for col in columns:
                if any(pattern in col.lower() for pattern in patterns_list):
                    mapping[standard_col] = col
                    break
        
        return mapping
    
    def _extract_wine_from_row(self, row: pd.Series, column_mapping: Dict[str, str]) -> Dict[str, Any]:
        """
        Estrae dati vino da una riga
        
        Args:
            row: Riga del DataFrame
            column_mapping: Mappatura delle colonne
            
        Returns:
            Dati vino o None
        """
        try:
            # Estrai nome
            name = self._get_column_value(row, column_mapping, 'name')
            if not name or pd.isna(name) or str(name).strip() == '':
                return None
            
            # Estrai produttore
            producer = self._get_column_value(row, column_mapping, 'producer')
            if not producer or pd.isna(producer):
                producer = 'Sconosciuto'
            
            # Estrai quantità
            quantity = self._get_column_value(row, column_mapping, 'quantity')
            if not quantity or pd.isna(quantity):
                quantity = 1
            else:
                try:
                    quantity = int(float(quantity))
                except (ValueError, TypeError):
                    quantity = 1
            
            # Estrai altri dati
            vintage = self._get_column_value(row, column_mapping, 'vintage')
            wine_type = self._get_column_value(row, column_mapping, 'wine_type')
            region = self._get_column_value(row, column_mapping, 'region')
            price = self._get_column_value(row, column_mapping, 'price')
            min_quantity = self._get_column_value(row, column_mapping, 'min_quantity')
            
            # Calcola scorta minima se non specificata
            if not min_quantity or pd.isna(min_quantity):
                min_quantity = max(1, quantity // 4)  # 25% della quantità
            else:
                try:
                    min_quantity = int(float(min_quantity))
                except (ValueError, TypeError):
                    min_quantity = max(1, quantity // 4)
            
            # Rileva tipo vino se non specificato
            if not wine_type or pd.isna(wine_type):
                wine_type = self._detect_wine_type(str(name))
            
            return {
                'name': str(name).strip(),
                'producer': str(producer).strip(),
                'quantity': quantity,
                'min_quantity': min_quantity,
                'vintage': int(vintage) if vintage and not pd.isna(vintage) else None,
                'wine_type': str(wine_type).strip() if wine_type and not pd.isna(wine_type) else 'rosso',
                'region': str(region).strip() if region and not pd.isna(region) else None,
                'cost_price': float(price) if price and not pd.isna(price) else None,
                'notes': f"Importato da file: {row.get('note', '')}" if 'note' in row else None
            }
            
        except Exception as e:
            self.logger.error(f"Errore estrazione vino da riga: {e}")
            return None
    
    def _get_column_value(self, row: pd.Series, column_mapping: Dict[str, str], key: str) -> Any:
        """
        Ottieni valore da una colonna mappata
        
        Args:
            row: Riga del DataFrame
            column_mapping: Mappatura delle colonne
            key: Chiave della mappatura
            
        Returns:
            Valore della colonna
        """
        if key in column_mapping:
            return row.get(column_mapping[key])
        return None
    
    def _detect_wine_type(self, name: str) -> str:
        """
        Rileva il tipo di vino dal nome
        
        Args:
            name: Nome del vino
            
        Returns:
            Tipo di vino
        """
        name_lower = name.lower()
        
        if any(word in name_lower for word in ['champagne', 'spumante', 'prosecco', 'franciacorta', 'cava']):
            return 'spumante'
        elif any(word in name_lower for word in ['bianco', 'white', 'chardonnay', 'pinot grigio', 'sauvignon']):
            return 'bianco'
        elif any(word in name_lower for word in ['rosato', 'rose', 'rosé', 'rosato']):
            return 'rosato'
        else:
            return 'rosso'  # Default
