import os
import sys
import glob
import json
from pathlib import Path
from colorama import Fore, init
from openai import OpenAI
from mlx_vomo import VomoMLX
import re

init(autoreset=True)

class DisciplineConsolidator:
    def __init__(self, base_folder):
        self.base_folder = Path(base_folder)
        self.vomo = VomoMLX() # Reuses VomoMLX for transcription/diarization
        
        # Load API Key for classification
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")
        self.client = OpenAI(api_key=api_key)
        
        # Buffer to hold consolidated text: {'DISCIPLINE_NAME': [segment1, segment2, ...]}
        self.consolidation_buffer = {}

    def scan_directory(self):
        """Finds all video/audio files in the directory"""
        extensions = ['*.mp4', '*.mp3', '*.m4a', '*.wav']
        files = []
        for ext in extensions:
            files.extend(self.base_folder.glob(ext))
        
        # Filter out problematic files
        files = [f for f in files if "04_Urbanistico_Constitucional" not in f.name]
        
        return sorted(list(set(files)))

    def ensure_transcription(self, file_path):
        """Ensures the file is transcribed and returns the path to RAW.txt"""
        file_path = Path(file_path)
        raw_txt_path = file_path.parent / f"{file_path.stem}_RAW.txt"
        
        if raw_txt_path.exists():
            print(f"{Fore.GREEN}   📂 Transcrição encontrada: {raw_txt_path.name}")
            return raw_txt_path
        
        print(f"{Fore.YELLOW}   🎙️  Transcrevendo: {file_path.name}...")
        try:
            # Optimize audio first
            audio_path = self.vomo.optimize_audio(str(file_path))
            # Transcribe
            transcription = self.vomo.transcribe(audio_path)
            
            # Save RAW
            with open(raw_txt_path, 'w', encoding='utf-8') as f:
                f.write(transcription)
                
            return raw_txt_path
        except Exception as e:
            print(f"{Fore.RED}   ❌ Falha ao transcrever {file_path.name}: {e}")
            return None

    def classify_discipline(self, text_segment):
        """Uses LLM to classify the discipline of a text segment"""
        if len(text_segment) < 5000:
            return "DESCONHECIDO" # Too short to classify reliably
            
        sample = text_segment[:4000] # Analyze first 4k chars for better context
        
        prompt = f"""Você é um classificador de disciplinas jurídicas para concursos de Procuradoria.

Classifique o texto abaixo em UMA das seguintes disciplinas (retorne APENAS o código exato):

- DIREITO_CONSTITUCIONAL (Organização do Estado, Direitos Fundamentais, Controle de Constitucionalidade)
- DIREITO_ADMINISTRATIVO (Atos Administrativos, Servidores, Bens Públicos, Responsabilidade do Estado)
- DIREITO_CIVIL (Contratos, Obrigações, Família, Sucessões, Responsabilidade Civil)
- PROCESSO_CIVIL (Recursos, Procedimentos, Jurisdição, Competência, Execução)
- DIREITO_DO_TRABALHO (CLT, Relações de Emprego, Direitos Trabalhistas - NÃO processual)
- PROCESSO_DO_TRABALHO (Reclamação Trabalhista, Recursos Trabalhistas - parte processual)
- DIREITO_EMPRESARIAL (Sociedades, Títulos de Crédito, Falência, Recuperação)
- DIREITO_EMPRESARIAL_PUBLICO (Empresas Estatais, Sociedades de Economia Mista, Controle de Estatais)
- DIREITO_TRIBUTARIO (Tributos, Impostos, Taxas, Contribuições, CTN)
- EXECUCAO_FISCAL (LEF, Execução de Dívida Ativa, CDA)
- DIREITO_FINANCEIRO (Orçamento Público, LOA, LDO, PPA, Precatórios)
- DIREITO_PREVIDENCIARIO (RGPS, Aposentadoria, Benefícios)
- DIREITO_AMBIENTAL (Meio Ambiente, Licenciamento, Crimes Ambientais)
- DIREITO_URBANISTICO (Estatuto da Cidade, Plano Diretor, Zoneamento)
- LGPD (Lei Geral de Proteção de Dados, Dados Pessoais, ANPD)
- LICITACOES_CONTRATOS (Lei 14.133, Pregão, Contratos Administrativos)

IMPORTANTE - NÃO CONFUNDIR:
❌ "Apresentação do curso" ou "organização da banca do concurso" NÃO é Direito Administrativo
❌ "Metodologia de estudos" ou "dicas de aprovação" NÃO é nenhuma disciplina jurídica
✅ Direito Administrativo = conteúdo JURÍDICO sobre atos administrativos, licitações, servidores, etc.

REGRAS:
1. Se o texto fala sobre DIREITO MATERIAL do trabalho (CLT, jornada, férias), classifique como DIREITO_DO_TRABALHO
2. Se o texto fala sobre PROCESSO do trabalho (reclamação, JT), classifique como PROCESSO_DO_TRABALHO
3. Se o texto fala sobre EMPRESAS ESTATAIS ou SOCIEDADES DE ECONOMIA MISTA, classifique como DIREITO_EMPRESARIAL_PUBLICO
4. Se for APENAS apresentação/metodologia/organização de curso SEM conteúdo jurídico, retorne DESCONHECIDO
5. Se misturar assuntos, escolha o PREDOMINANTE no texto
6. Só classifique como uma disciplina se houver CONTEÚDO JURÍDICO SUBSTANTIVO daquela área

TEXTO:
{sample}

RESPOSTA (apenas o código):"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini-2025-08-07",
                messages=[{"role": "user", "content": prompt}]
            )
            discipline = response.choices[0].message.content.strip().upper().replace(" ", "_")
            # Basic cleanup
            discipline = re.sub(r'[^A-Z_]', '', discipline)
            return discipline
        except Exception as e:
            print(f"{Fore.RED}   ⚠️ Erro na classificação: {e}")
            return "DESCONHECIDO"

    def process_file(self, file_path):
        print(f"\n{Fore.CYAN}Processando: {file_path.name}")
        
        # 1. Ensure Transcription
        raw_path = self.ensure_transcription(file_path)
        if not raw_path: return
        
        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
            
        # 2. Segment by Speaker
        segments = self.vomo._segment_raw_transcription(raw_text)
        if not segments:
            segments = [{'speaker': 'SPEAKER 1', 'content': raw_text}]
            
        # 3. Classify and Buffer
        for i, seg in enumerate(segments):
            speaker = seg['speaker']
            content = seg['content']
            
            # For large segments (>100k chars), use sliding window to detect discipline transitions
            LARGE_SEGMENT_THRESHOLD = 100000
            WINDOW_SIZE = 15000  # 15k chars per classification window
            STEP_SIZE = 10000    # 10k step (5k overlap for better transition detection)
            
            if len(content) > LARGE_SEGMENT_THRESHOLD:
                print(f"   ⚠️  Segmento grande ({len(content)} chars) - detectando transições de disciplina...")
                
                # Classify windows with overlap to detect transitions
                window_classifications = []
                for start in range(0, len(content), STEP_SIZE):
                    window = content[start:start + WINDOW_SIZE]
                    if len(window) > 5000:
                        discipline = self.classify_discipline(window)
                        window_classifications.append({
                            'start': start,
                            'end': min(start + WINDOW_SIZE, len(content)),
                            'discipline': discipline
                        })
                
                if not window_classifications:
                    continue
                    
                # Group consecutive windows with same discipline
                discipline_segments = []
                current_segment = {
                    'discipline': window_classifications[0]['discipline'],
                    'start': window_classifications[0]['start'],
                    'end': window_classifications[0]['end']
                }
                
                for w in window_classifications[1:]:
                    if w['discipline'] == current_segment['discipline']:
                        # Extend current segment
                        current_segment['end'] = w['end']
                    else:
                        # Save current segment and start new one
                        discipline_segments.append(current_segment)
                        current_segment = {
                            'discipline': w['discipline'],
                            'start': w['start'],
                            'end': w['end']
                        }
                discipline_segments.append(current_segment)
                
                # Log transitions found
                print(f"      Encontradas {len(discipline_segments)} seções:")
                for seg in discipline_segments:
                    discipline = seg['discipline']
                    size = seg['end'] - seg['start']
                    print(f"         {Fore.MAGENTA}{discipline}{Fore.RESET} ({size//1000}k chars)")
                
                # Add each discipline's content to buffer
                for seg in discipline_segments:
                    discipline = seg['discipline']
                    if discipline in ["DESCONHECIDO"]:
                        continue
                        
                    segment_content = content[seg['start']:seg['end']]
                    
                    if discipline not in self.consolidation_buffer:
                        self.consolidation_buffer[discipline] = []
                    
                    header = f"\n\n{'='*40}\nFONTE: {file_path.name} | {speaker}\n{'='*40}\n\n"
                    self.consolidation_buffer[discipline].append(header + segment_content)
            else:
                # Normal classification for smaller segments
                print(f"   Analizando {speaker} ({len(content)} chars)...")
                discipline = self.classify_discipline(content)
                print(f"   🏷️  Classificado como: {Fore.MAGENTA}{discipline}")
                
                if discipline not in ["DESCONHECIDO"]:
                    if discipline not in self.consolidation_buffer:
                        self.consolidation_buffer[discipline] = []
                    
                    header = f"\n\n{'='*40}\nFONTE: {file_path.name} | {speaker}\n{'='*40}\n\n"
                    self.consolidation_buffer[discipline].append(header + content)
        
        # Save incrementally
        self.save_consolidated_files()

    def save_consolidated_files(self):
        print(f"\n{Fore.GREEN}{'='*60}")
        print(f"💾 Salvando arquivos consolidados...")
        print(f"{'='*60}")
        
        for discipline, contents in self.consolidation_buffer.items():
            filename = f"{discipline}_CONSOLIDADO_RAW.txt"
            output_path = self.base_folder / filename
            
            # Append if exists, or create new? 
            # Let's overwrite for now to avoid duplication if run multiple times, 
            # or maybe append if we want to build up. 
            # Given the request "consolidate... for later editing", overwriting a fresh consolidation seems safer to avoid duplicates.
            
            full_text = "".join(contents)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
                
            print(f"   📄 {filename}: {len(contents)} segmentos")

    def run(self):
        files = self.scan_directory()
        print(f"{Fore.CYAN}Encontrados {len(files)} arquivos para processar.")
        
        for f in files:
            self.process_file(f)
            
        self.save_consolidated_files()

if __name__ == "__main__":
    target_folder = "Aulas_PGM_RJ"
    if len(sys.argv) > 1:
        target_folder = sys.argv[1]
        
    consolidator = DisciplineConsolidator(target_folder)
    consolidator.run()
