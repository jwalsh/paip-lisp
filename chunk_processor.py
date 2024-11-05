import os
import math
import click
import tiktoken
import requests
import json
import subprocess
from typing import Optional, List, Dict
from pathlib import Path

class ChunkProcessor:
    DEFAULT_SAFETY_FACTOR = 0.5  # Class constant for default safety level
    
    def __init__(self, model="claude-3-sonnet-20240229", safety_factor=None):
        self.model = model
        # Base limits (theoretical maximums)
        self.context_limits = {
            "claude-3-sonnet-20240229": 200000,  # Full 200k
            "gpt-4": 8192,                       # Full 8k
            "gpt-3.5-turbo": 4096,              # Full 4k
        }
        # Use provided safety factor, env var, or default
        self.safety_factor = (
            safety_factor or 
            float(os.getenv('CHUNK_SAFETY_FACTOR', self.DEFAULT_SAFETY_FACTOR))
        )
        self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def get_effective_limit(self):
        """Get the effective token limit applying safety factor"""
        base_limit = self.context_limits[self.model]
        return int(base_limit * self.safety_factor)

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        return len(self.tokenizer.encode(text))

    def process_file(self, input_file: Path, num_chunks: Optional[int] = None, interactive: bool = False):
        """Process input file into chunks with line count validation"""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Count original lines
                original_lines = content.count('\n')
        except FileNotFoundError:
            click.echo(f"Error: File {input_file} not found", err=True)
            return
        except UnicodeDecodeError:
            click.echo(f"Error: File {input_file} is not valid UTF-8", err=True)
            return

        # Get token stats
        total_tokens = self.estimate_tokens(content)
        effective_limit = self.get_effective_limit()
        
        click.echo(f"\nFile Statistics:")
        click.echo(f"File: {input_file}")
        click.echo(f"Total characters: {len(content):,}")
        click.echo(f"Total lines: {original_lines:,}")
        click.echo(f"Estimated tokens: {total_tokens:,}")
        click.echo(f"Effective token limit: {effective_limit:,}")

        # Calculate chunks needed
        min_chunks = math.ceil(total_tokens / effective_limit)
        if num_chunks is None or num_chunks < min_chunks:
            num_chunks = min_chunks
        
        click.echo(f"\nSplitting into {num_chunks} chunks...")

        # Create chunks directory
        chunks_dir = Path('chunks')
        chunks_dir.mkdir(exist_ok=True)
        
        # Calculate chunk size
        chunk_size = math.ceil(len(content) / num_chunks)
        
        chunks_info = []
        current_pos = 0
        total_chunk_lines = 0

        for i in range(num_chunks):
            if current_pos >= len(content):
                break

            # Get chunk with smart splitting
            end_pos = min(current_pos + chunk_size, len(content))
            chunk = content[current_pos:end_pos]
            
            if i < num_chunks - 1 and end_pos < len(content):
                last_period = chunk.rfind('.\n')
                last_newline = chunk.rfind('\n\n')
                split_point = max(last_period, last_newline)
                
                if split_point != -1:
                    end_pos = current_pos + split_point + 2
                    chunk = content[current_pos:end_pos]
            
            # Write chunk and count lines
            chunk_file = chunks_dir / f'chunk_{i+1}.txt'
            chunk_file.write_text(chunk)
            chunk_lines = chunk.count('\n')
            total_chunk_lines += chunk_lines
            
            tokens = self.estimate_tokens(chunk)
            chunks_info.append({
                'file': chunk_file,
                'chars': len(chunk),
                'tokens': tokens,
                'lines': chunk_lines,
                'content': chunk
            })
            
            click.echo(f"\nChunk {i+1}:")
            click.echo(f"- File: {chunk_file}")
            click.echo(f"- Lines: {chunk_lines:,}")
            click.echo(f"- Characters: {len(chunk):,}")
            click.echo(f"- Tokens: {tokens:,}")
            click.echo(f"- Token limit: {tokens:,}/{effective_limit:,}")
            
            current_pos = end_pos

        # Validate total lines
        click.echo("\nLine count validation:")
        click.echo(f"Original file: {original_lines:,} lines")
        click.echo(f"Sum of chunks: {total_chunk_lines:,} lines")
        if original_lines != total_chunk_lines:
            click.echo(f"Warning: Lost {original_lines - total_chunk_lines} lines during chunking!", err=True)

        if interactive:
            self.process_interactively(chunks_info)

        return chunks_info

    def process_interactively(self, chunks_info: List[dict]):
        """Process chunks interactively with clipboard integration"""
        for i, chunk_info in enumerate(chunks_info, 1):
            click.echo(f"\nProcessing Chunk {i}/{len(chunks_info)}")
            click.echo(f"Lines: {chunk_info['lines']:,}")
            click.echo(f"Tokens: {chunk_info['tokens']:,}")
            
            try:
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                process.communicate(chunk_info['content'].encode())
            except subprocess.SubprocessError:
                click.echo("Error: Failed to copy to clipboard", err=True)
                if not click.confirm("Continue anyway?"):
                    return
            
            if not click.confirm(
                f"Chunk {i} is in clipboard. Continue to next chunk?", 
                default=True
            ):
                return

class LittleLisperConverter:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL = "llama3.2:latest"
    
    def __init__(self):
        self.chunks: List[Dict] = []
        self.org_sections: List[str] = []

    def check_ollama(self) -> bool:
        """Verify Ollama is running and model is available"""
        try:
            response = requests.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(m["name"] == self.MODEL for m in models)
            return False
        except requests.RequestException:
            return False

    def convert_chunk(self, chunk: str) -> str:
        """Convert a chunk of text to Little Schemer style org-mode"""
        prompt = f"""In org-mode with Babel and Tangle (use :mkdirp t to ensure examples don't pollute) make A Little Schemer version of the attached:

{chunk}

The response should be valid org-mode with:
1. Question and Answer format
2. Code blocks using #+begin_src lisp and proper tangling
3. Clear progressive learning style
4. Each concept building on previous ones
"""
        
        response_text = ""
        try:
            response = requests.post(
                self.OLLAMA_URL,
                json={"model": self.MODEL, "prompt": prompt},
                stream=True
            )
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    response_text += data.get("response", "")
                    
        except requests.RequestException as e:
            click.echo(f"Error calling Ollama: {e}", err=True)
            return ""
            
        return response_text

    def stitch_org_file(self, output_file: str = "little-lisper-paip.org"):
        """Combine all org sections into a single file"""
        header = """#+TITLE: A Little Schemer's Guide to AI Programming
#+AUTHOR: Generated from PAIP by Peter Norvig
#+OPTIONS: ^:nil
#+PROPERTY: header-args:lisp :mkdirp t :tangle yes

"""
        with open(output_file, "w") as f:
            f.write(header)
            for i, section in enumerate(self.org_sections, 1):
                f.write(f"\n* Chapter {i}\n")
                f.write(section)
                f.write("\n")

def convert_to_little_lisper(chunks_info: List[dict]) -> str:
    """Convert chunks to Little Lisper style and combine"""
    converter = LittleLisperConverter()
    
    if not converter.check_ollama():
        click.echo("Error: Ollama not running or llama2 model not available", err=True)
        return None
        
    with click.progressbar(chunks_info, 
                          label='Converting to Little Lisper style') as chunks:
        for chunk in chunks:
            org_content = converter.convert_chunk(chunk['content'])
            converter.org_sections.append(org_content)
    
    converter.stitch_org_file()
    click.echo(f"\nCreated little-lisper-paip.org")
    return "little-lisper-paip.org"

@click.command()
@click.argument('filename', type=click.Path(exists=True), default='PAIP.txt')
@click.option('-n', '--num-chunks', type=int, help='Number of chunks to split into')
@click.option('-i', '--interactive', is_flag=True, help='Process chunks interactively')
@click.option('-m', '--model', default='claude-3-sonnet-20240229', 
              help='Model to use for token limits')
@click.option('-s', '--safety-factor', type=float,
              help=f'Factor to multiply context window by (default: {ChunkProcessor.DEFAULT_SAFETY_FACTOR})')
@click.option('--little-lisper', is_flag=True, 
              help='Convert chunks to Little Schemer style org-mode')
def main(filename: str, num_chunks: Optional[int], interactive: bool, 
         model: str, safety_factor: float, little_lisper: bool):
    """Split a text file into chunks suitable for LLM processing.
    
    If FILENAME is not specified, defaults to PAIP.txt
    
    The safety factor determines what portion of the model's maximum context
    window to use. Default is 0.5 (50%). Can be overridden with -s option
    or CHUNK_SAFETY_FACTOR environment variable.
    """
    processor = ChunkProcessor(model=model, safety_factor=safety_factor)
    
    # Show effective limits
    click.echo(f"\nToken Limits:")
    click.echo(f"Model maximum: {processor.context_limits[model]:,}")
    click.echo(f"Safety factor: {processor.safety_factor:.1%}")
    click.echo(f"Effective limit: {processor.get_effective_limit():,}")
    
    chunks_info = processor.process_file(
        Path(filename),
        num_chunks=num_chunks,
        interactive=interactive
    )
    
    if little_lisper and chunks_info:
        convert_to_little_lisper(chunks_info)

if __name__ == "__main__":
    main()
