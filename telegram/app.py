# Standard library
import asyncio
import os
import sys
from contextlib import suppress


sys.dont_write_bytecode = True

# First party
from bot.main import main  # noqa


if __name__ == '__main__':
    with suppress(KeyboardInterrupt):

    # Polling
        if os.name != 'nt':
            # Third party
            import uvloop

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

        asyncio.run(main())