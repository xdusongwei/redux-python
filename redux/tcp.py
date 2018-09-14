import asyncio
from .framework import Option


class TcpMedium:
    async def connect(self, host, port) -> Option:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            return Option((reader, writer))
        except Exception as e:
            return Option(e)

    async def listen(self, host, port, handler) -> Option:
        try:
            server = await asyncio.start_server(handler, host, port)
            return Option(server)
        except Exception as e:
            return Option(e)

    async def write(self, writer, data):
        try:
            writer.write(data)
            await writer.drain()
            return Option()
        except Exception as e:
            return Option(e)

    async def read(self, reader, n=-1):
        try:
            data = await reader.read(n)
            return Option(data)
        except Exception as e:
            return Option(e)

    def close_writer(self, writer):
        try:
            writer.close()
            return Option()
        except Exception as e:
            return Option(e)

    async def close_listen(self, server):
        try:
            server.close()
            await server.wait_closed()
            return Option()
        except Exception as e:
            return Option(e)

