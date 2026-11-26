
from collections.abc import Iterator
from typing import Mapping, NamedTuple
from types import MappingProxyType
from html.parser import HTMLParser
from urllib.parse import urljoin


class Node(NamedTuple):
    """Nodo inmutable del árbol HTML.

    ``tag`` guarda el nombre de la etiqueta, ``attrs`` sus atributos y
    ``children`` los nodos o fragmentos de texto que contiene.
    """

    tag: str
    attrs: Mapping[str, str]
    children: tuple["Node | str", ...]

    def get(self, att: str):
        val = self.attrs.get(att)
        if val is None:
            return None
        val = val.strip()
        if len(val) == 0:
            return None
        return val

    def get_absolute(self, base_url: str, att: str):
        val = self.get(att)
        if val is None:
            return None
        return urljoin(base_url, val)

    def _text(self) -> str:
        """Concatena el texto propio y el de los nodos descendientes.

        Omite los fragmentos vacíos o que solo contienen espacios y separa
        los fragmentos restantes con un espacio. Es un auxiliar interno de
        :meth:`text`.
        """
        parts = []
        for child in self.children:
            value = child if isinstance(child, str) else child._text()
            if value.strip():
                parts.append(value.strip())
        text = " ".join(parts)
        return text

    def text(self):
        """Devuelve el texto del nodo sin espacios al principio o al final.

        El texto incluye el de todos sus descendientes. Devuelve ``None`` si
        el nodo no contiene texto significativo.
        """
        text = self._text()
        text = text.strip()
        if len(text) == 0:
            return None
        return text

    def descendants(
        self,
        tag: str | tuple[str, ...] | None,
        *class_names: str,
    ) -> Iterator["Node"]:
        """Itera por este nodo y sus descendientes en orden de documento.

        Si se proporciona ``tag``, solo produce nodos con ese nombre. Si es
        ``None``, produce todos los nodos, empezando por este mismo nodo.
        """
        if tag is None or (
            isinstance(tag, str) and self.tag == tag
        ) or (
            isinstance(tag, tuple) and self.tag in tag
        ):
            if self.has_class(*class_names):
                yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.descendants(tag, *class_names)

    def descendants_text(
        self,
        tag: str | tuple[str, ...] | None,
        *class_names: str,
    ):
        for n in self.descendants(tag, *class_names):
            text = n.text()
            if text:
                yield text

    def first(
        self,
        tag: str | None,
        *class_names: str
    ):
        for node in self.descendants(tag, *class_names):
            return node

    def first_text(
        self,
        tag: str | None,
        *class_names: str
    ):
        for node in self.descendants(tag, *class_names):
            return node.text()

    def get_classes(self):
        cls = self.attrs.get("class")
        if not cls:
            return tuple()
        return tuple(cls.strip().split())

    def has_class(self, *names: str) -> bool:
        cls = self.get_classes()
        for c in names:
            if c not in cls:
                return False
        return True


class TreeParser(HTMLParser):
    """Construye un árbol usando los eventos de ``HTMLParser``."""

    # Etiquetas HTML sin contenido ni etiqueta de cierre.
    VOID_TAGS = (
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    )

    @classmethod
    def parse(cls, html: str):
        parser = cls()
        parser.feed(html)
        root = parser.finish()
        return root

    def __init__(self) -> None:
        """Inicializa el parser y las estructuras temporales del árbol.

        La pila mantiene el nodo que recibe los siguientes datos o etiquetas;
        ``__child_lists`` acumula los hijos hasta llamar a :meth:`finish`.
        """
        super().__init__(convert_charrefs=True)
        self.__root = Node(
            "document",
            MappingProxyType({}),
            (),
        )
        self.__stack = [self.__root]
        self.__child_lists: dict[int, list[Node | str]] = {
            id(self.__root): []
        }

    def finish(self) -> Node:
        """Devuelve la raíz del árbol convertida a estructura inmutable.

        Llama a este método después de alimentar el parser con el HTML. Los
        atributos y los hijos del árbol resultante no se pueden modificar.
        """
        return self.__freeze(self.__root)

    def __freeze(self, node: Node) -> Node:
        """Crea una copia inmutable de ``node`` y de todo su subárbol.

        Los hijos se leen de ``__child_lists``, donde se fueron acumulando
        durante el análisis, y se almacenan como una tupla en cada nuevo nodo.
        """
        children = tuple(
            self.__freeze(child) if isinstance(child, Node) else child
            for child in self.__child_lists[id(node)]
        )
        return Node(node.tag, node.attrs, children)

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Añade una etiqueta de apertura al nodo actual.

        ``HTMLParser`` invoca este método por cada etiqueta normal de apertura.
        Los atributos se guardan en un mapa de solo lectura. Las etiquetas que
        no son vacías se apilan para que su contenido se añada dentro de ellas.
        """
        node = Node(
            tag,
            MappingProxyType({
                key: value or ""
                for key, value
                in attrs
            }),
            (),
        )
        self.__child_lists[id(self.__stack[-1])].append(node)
        self.__child_lists[id(node)] = []
        if tag not in TreeParser.VOID_TAGS:
            self.__stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Procesa una etiqueta autocerrada, por ejemplo ``<br />``.

        Primero crea el nodo mediante :meth:`handle_starttag`; luego lo quita
        de la pila si esa etiqueta se había apilado.
        """
        self.handle_starttag(tag, attrs)
        if tag not in TreeParser.VOID_TAGS:
            self.__stack.pop()

    def handle_endtag(self, tag: str) -> None:
        """Cierra la etiqueta indicada retirándola de la pila.

        Busca desde el nodo más interno hacia la raíz y descarta de la pila la
        etiqueta encontrada y cualquier elemento mal cerrado que estuviera
        dentro. Si no encuentra la etiqueta, no modifica la pila.
        """
        for index in range(len(self.__stack) - 1, 0, -1):
            if self.__stack[index].tag == tag:
                del self.__stack[index:]
                break

    def handle_data(self, data: str) -> None:
        """Añade un fragmento de texto como hijo del nodo actual.

        ``HTMLParser`` puede entregar el contenido en uno o varios fragmentos;
        el texto se acumula tal como llega y se combina al consultar el nodo.
        """
        if data:
            self.__child_lists[id(self.__stack[-1])].append(data)
