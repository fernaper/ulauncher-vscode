import logging
import os
import subprocess

from pathlib import Path, PosixPath
from typing import List, Optional
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.action.ActionList import ActionList
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction
from ulauncher.api.shared.event import ItemEnterEvent, KeywordQueryEvent, PreferencesEvent, PreferencesUpdateEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem

# create an instance of logger at a module level
logger = logging.getLogger(__name__)

LIMIT_FOLDERS_TO_SHOW = 10


class OpenFolder():
    def __init__(self, folder: PosixPath):
        self.folder = folder


def is_hidden(folder: PosixPath) -> bool:
    return folder.name[0].startswith('.')


class VsFolderExtension(Extension):

    def __init__(self):
        super().__init__()
        self.home: Optional[PosixPath] = Path.home()
        self.show_hidden: bool = False
        self.subscribe(PreferencesEvent, OnLoad())
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())
        self.subscribe(PreferencesUpdateEvent,
                       PreferencesUpdateEventListener())


class OnLoad(EventListener):

    def on_event(self, event: PreferencesEvent, extension: VsFolderExtension):
        home = event.preferences.get('home_input')
        logger.debug(f'HOME IS: {home}')
        if home is not None:
            home = home.strip()
        if home is not None and Path(home).exists():
            extension.home = Path(home)

        extension.show_hidden = event.preferences.get('show_hidden').lower() in (
            'true', 't', 'y', 'yes', '1'
        )


class KeywordQueryEventListener(EventListener):

    def on_event(self, event: KeywordQueryEvent, extension: VsFolderExtension):
        arg = event.get_argument()

        if arg is None:
            arg = ''

        # absolute path
        if arg.startswith(os.sep) and arg.rfind(os.sep) == 0:
            folder = Path('/')
            arg = arg[1:]
        elif arg.startswith(os.sep):
            parts = arg.rsplit(os.sep, 1)
            folder = Path(parts[0])
            arg = parts[-1]
        elif '~/' in arg:
            folder = Path.home()
            arg = arg[arg.index('~/')+2:]
        else:
            folder = extension.home

        return RenderResultListAction(
            build_list_of_folders(
                extension, folder, arg, LIMIT_FOLDERS_TO_SHOW
            )
        )


class ItemEnterEventListener(EventListener):

    def on_event(self, event: ItemEnterEvent, extension: VsFolderExtension):
        arg = event.get_data()
        if isinstance(arg, OpenFolder):
            subprocess.run(['code', f'{arg.folder}{os.sep}'])
            return HideWindowAction()
        return RenderResultListAction(
            build_list_of_folders(
                extension, arg, '', LIMIT_FOLDERS_TO_SHOW
            )
        )


class PreferencesUpdateEventListener(EventListener):

    def on_event(self, event: PreferencesUpdateEvent, extension: VsFolderExtension):
        new_value = event.new_value
        if event.id == 'home_input':
            new_value = new_value.strip()
            logger.info(f'Updated home to: {new_value}')
            if not new_value:
                extension.home = Path.home()
            else:
                extension.home = Path(new_value)
        elif event.id == 'show_hidden':
            extension.show_hidden = event.new_value.lower() in (
                'true', 't', 'y', 'yes', '1'
            )


def build_list_of_folders(
    extension: VsFolderExtension,
    folder: PosixPath, arg: str,
    limit_folders_to_show: int = 5
) -> List[ExtensionResultItem]:
    # access subfolders in case of complete string
    if os.sep in arg:
        extra_path = arg.split(os.sep)
        initial_part = extra_path[:-1]
        logger.info(f'List of folders: {folder}')
        folder = folder.joinpath(*initial_part)
        arg = extra_path[-1]

    logger.debug(f'')
    lower_arg = arg.lower()
    folders = []
    if folder.exists():
        folders = sorted(
            [
                folder
                for folder in folder.iterdir()
                if (extension.show_hidden or not is_hidden(folder)) and not folder.is_file()
                and lower_arg in folder.name.lower()
                and folder.exists()
            ],
            key=lambda folder: - folder.stat().st_mtime
        )

    vs_keyword = extension.preferences.get('vs_kw')
    home = str(extension.home) + os.sep
    try_relative_folder = str(folder)
    if try_relative_folder.startswith(home):
        try_relative_folder = try_relative_folder.replace(home, '', 1)

    items = [
        ExtensionResultItem(
            icon='images/open-folder.png',
            name='Open current folder',
            description=f'Vs folder: {folder}',
            on_enter=ExtensionCustomAction(
                OpenFolder(folder), keep_app_open=False),
        ),
        ExtensionResultItem(
            icon='images/inner-folder.png',
            name='Go to parent',
            description=f'Vs folder: {folder.parent}',
            on_enter=ActionList([
                SetUserQueryAction(
                    f'{vs_keyword} {try_relative_folder}{os.sep}..{os.sep}'
                ),
                ExtensionCustomAction(folder, keep_app_open=True)
            ]),
        )
    ]

    for folder in folders[:limit_folders_to_show]:
        try_relative_folder = str(folder)
        if try_relative_folder.startswith(home):
            try_relative_folder = try_relative_folder.replace(home, '', 1)

        items.append(
            ExtensionResultItem(
                icon='images/inner-folder.png',
                name=try_relative_folder,
                description=f'Vs folder: {folder}',
                on_enter=ActionList([
                    SetUserQueryAction(
                        f'{vs_keyword} {try_relative_folder}{os.sep}'
                    ),
                    ExtensionCustomAction(folder, keep_app_open=True)
                ]),
            )
        )

    return items


if __name__ == '__main__':
    VsFolderExtension().run()
