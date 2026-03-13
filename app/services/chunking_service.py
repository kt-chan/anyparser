import re
import uuid
import tiktoken
import mistletoe
from mistletoe.block_token import Heading, Paragraph, List as MDList, ListItem, Table, CodeFence, Quote, HTMLBlock, Document
from mistletoe.markdown_renderer import MarkdownRenderer
from typing import List, Dict, Any, Optional
from loguru import logger

class SemanticSection:
    """Core AST Node representing either a structural heading or a content leaf."""
    def __init__(self, title: str, level: int, content: str = ""):
        self.node_id: str = str(uuid.uuid4())
        self.title: str = title
        self.level: int = level
        self.own_content: str = content
        
        # Bi-directional pointers
        self.parent: Optional['SemanticSection'] = None
        self.children: List['SemanticSection'] = []
        self.next_sibling: Optional['SemanticSection'] = None
        self.prev_sibling: Optional['SemanticSection'] = None
        
        # Local Inventory
        self.image_count: int = 0
        self.table_count: int = 0
        self.code_block_count: int = 0
        self.token_count: int = 0
        
        # Aggregated Statistics
        self.total_descendants: int = 0
        self.total_token_count: int = 0
        self.has_tables_in_subtree: bool = False
        self.has_images_in_subtree: bool = False

    def add_child(self, child: 'SemanticSection') -> None:
        child.parent = self
        if self.children:
            last_child = self.children[-1]
            last_child.next_sibling = child
            child.prev_sibling = last_child
        self.children.append(child)

    def aggregate_statistics(self, tokenizer) -> None:
        self.token_count = len(tokenizer.encode(self.own_content)) if self.own_content else 0
        self.total_token_count = self.token_count
        self.total_descendants = len(self.children)
        self.has_tables_in_subtree = self.table_count > 0
        self.has_images_in_subtree = self.image_count > 0

        for child in self.children:
            child.aggregate_statistics(tokenizer)
            self.total_token_count += child.total_token_count
            self.total_descendants += child.total_descendants
            self.has_tables_in_subtree |= child.has_tables_in_subtree
            self.has_images_in_subtree |= child.has_images_in_subtree

    def get_ancestors(self) -> List['SemanticSection']:
        ancestors, current = [], self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors[::-1]

    def get_breadcrumb_path(self) -> str:
        path = [node.title for node in self.get_ancestors() if node.title and node.title != "Document Root"]
        if self.title and self.title != "Document Root": path.append(self.title)
        return " > ".join(path)

    def to_rag_document(self) -> Dict[str, Any]:
        return {
            "content": self.own_content,
            "metadata": {
                "id": self.node_id,
                "title": self.title,
                "breadcrumbs": self.get_breadcrumb_path().split(" > ") if self.get_breadcrumb_path() else [],
                "level": self.level,
                "tokens": self.token_count,
                "total_tokens_in_subtree": self.total_token_count,
                "has_table": self.has_tables_in_subtree,
                "has_image": self.has_images_in_subtree,
            }
        }

class ChunkingService:
    def __init__(self):
        # Initialize tokenizer
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to load cl100k_base encoding, falling back to gpt2: {e}")
            self.tokenizer = tiktoken.get_encoding("gpt2")
        
        self.renderer = MarkdownRenderer()

    def _is_contextual_description(self, text: str) -> bool:
        """Checks if the text contains a contextual description tag."""
        return "<IMAGE_CONTEXTUAL_DESCRIPTION>" in text or "<TABLE_CONTEXTUAL_DESCRIPTION>" in text

    def _contains_image(self, node) -> bool:
        """Recursively check if a node contains an image span token."""
        from mistletoe.span_token import Image
        if isinstance(node, Image):
            return True
        if hasattr(node, 'children') and isinstance(node.children, (list, tuple)):
            for child in node.children:
                if self._contains_image(child):
                    return True
        return False

    async def chunk_markdown(self, markdown_text: str, max_chunk_tokens: int) -> List[Dict[str, Any]]:
        """
        Chunks a markdown string into semantic parts using mistletoe AST (Tree Pass).
        """
        try:
            with self.renderer:
                # 1. Parse into mistletoe Document
                doc = mistletoe.Document(markdown_text)
                
                # 2. Build the structural tree
                root_node = self._build_tree(doc)
                
                # 3. Smart chunking (Merge & Split leaf nodes)
                self._prune_and_chunk(root_node, max_chunk_tokens)
                
                # 4. Bubble up RAG statistics
                root_node.aggregate_statistics(self.tokenizer)
                
                # 5. Export only the content leaf nodes
                rag_docs = []
                for node in self._get_leaf_nodes(root_node):
                    if node.own_content.strip():
                        rag_docs.append(node.to_rag_document())
                        
                return rag_docs
        except Exception as e:
            logger.error(f"Error during semantic chunking: {e}")
            return [{"content": markdown_text, "metadata": {"breadcrumbs": [], "error": str(e)}}]

    def _build_tree(self, doc: Document) -> SemanticSection:
        """Infers hierarchy from flat markdown and attaches content as leaf children."""
        root = SemanticSection(title="Document Root", level=0)
        active_headings = {0: root}

        for child in doc.children:
            if isinstance(child, Heading):
                level = child.level
                # Render heading to get text
                title = self.renderer.render(child).strip().lstrip('#').strip()
                new_section = SemanticSection(title=title, level=level)
                
                # Find closest structural parent
                parent_level = level - 1
                while parent_level > 0 and parent_level not in active_headings:
                    parent_level -= 1
                
                active_headings[parent_level].add_child(new_section)
                active_headings[level] = new_section
                
                # Clear deeper transient headings
                for k in list(active_headings.keys()):
                    if k > level: del active_headings[k]
            else:
                # It's a content block -> Treat as a Leaf Node
                content = self.renderer.render(child).strip()
                if not content: continue
                
                deepest_level = max(active_headings.keys())
                parent = active_headings[deepest_level]
                
                leaf_node = SemanticSection(title="", level=parent.level + 1, content=content)
                
                # Flags for atomic units
                if isinstance(child, Table) or "<table" in content.lower():
                    leaf_node.table_count = 1
                if self._contains_image(child) or "<IMAGE_" in content:
                    leaf_node.image_count = 1
                if isinstance(child, CodeFence) or "<CODE_" in content:
                    leaf_node.code_block_count = 1
                    
                parent.add_child(leaf_node)
                
        return root

    def _prune_and_chunk(self, node: SemanticSection, limit: int) -> None:
        """Post-order traversal to merge small siblings and split oversized ones."""
        new_children = []
        current_merged_leaf = None

        for child in node.children:
            if child.title: # It's a structural branch, recurse into it
                if current_merged_leaf:
                    new_children.append(current_merged_leaf)
                    current_merged_leaf = None
                self._prune_and_chunk(child, limit)
                new_children.append(child)
            else: # It's a content leaf
                child_tokens = len(self.tokenizer.encode(child.own_content))
                child.token_count = child_tokens
                
                if current_merged_leaf is None:
                    current_merged_leaf = child
                else:
                    # Merge Condition: fits in limit OR is a contextual description (must bind)
                    is_contextual = self._is_contextual_description(child.own_content)
                    if is_contextual or (current_merged_leaf.token_count + child_tokens <= limit):
                        joiner = "\n" if is_contextual else "\n\n"
                        current_merged_leaf.own_content += joiner + child.own_content
                        current_merged_leaf.token_count = len(self.tokenizer.encode(current_merged_leaf.own_content))
                        current_merged_leaf.table_count += child.table_count
                        current_merged_leaf.image_count += child.image_count
                        current_merged_leaf.code_block_count += child.code_block_count
                    else:
                        # Flush current and start a new merged block
                        new_children.append(current_merged_leaf)
                        current_merged_leaf = child

        if current_merged_leaf:
            new_children.append(current_merged_leaf)

        # Split Condition for oversized leaf nodes
        final_children = []
        for child in new_children:
            is_atomic = child.table_count > 0 or child.image_count > 0 or child.code_block_count > 0
            if child.title == "" and child.token_count > limit and not is_atomic:
                # Split large paragraphs at sentence boundaries
                sentences = re.split(r'(?<=[.!?])[\s\n]+', child.own_content)
                temp_content = ""
                for s in sentences:
                    s_tokens = len(self.tokenizer.encode(s))
                    if len(self.tokenizer.encode(temp_content)) + s_tokens > limit and temp_content:
                        split_leaf = SemanticSection(title="", level=child.level, content=temp_content.strip())
                        final_children.append(split_leaf)
                        temp_content = s
                    else:
                        temp_content += (" " if temp_content else "") + s
                if temp_content:
                    split_leaf = SemanticSection(title="", level=child.level, content=temp_content.strip())
                    final_children.append(split_leaf)
            else:
                final_children.append(child)

        # Re-attach the pruned/split children ensuring sibling links are re-calculated
        node.children = []
        for child in final_children:
            node.add_child(child)

    def _get_leaf_nodes(self, node: SemanticSection) -> List[SemanticSection]:
        """Utility to extract purely content-bearing nodes."""
        leaves = []
        if node.title == "" and node.own_content: leaves.append(node)
        for child in node.children:
            leaves.extend(self._get_leaf_nodes(child))
        return leaves
