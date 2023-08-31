import random
from collections import Counter
from pathlib import Path

import imagesize
from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMessageBox

from utils.image import Image


class ImageListModel(QAbstractListModel):
    def __init__(self, image_list_image_width: int, separator: str):
        super().__init__()
        self.image_list_image_width = image_list_image_width
        self.separator = separator
        self.images = []

    def rowCount(self, parent=None) -> int:
        return len(self.images)

    def data(self, index, role=None) -> Image | str | QIcon | QSize:
        image = self.images[index.row()]
        if role == Qt.UserRole:
            return image
        if role == Qt.DisplayRole:
            # The text shown next to the thumbnail in the image list.
            text = image.path.name
            if image.tags:
                caption = self.separator.join(image.tags)
                text += f'\n{caption}'
            return text
        if role == Qt.DecorationRole:
            # The thumbnail. If the image already has a thumbnail stored, use
            # it. Otherwise, generate a thumbnail and save it to the image.
            if image.thumbnail:
                return image.thumbnail
            thumbnail = QIcon(
                QPixmap(str(image.path)).scaledToWidth(
                    self.image_list_image_width))
            image.thumbnail = thumbnail
            return thumbnail
        if role == Qt.SizeHintRole:
            dimensions = image.dimensions
            if dimensions:
                width, height = dimensions
                # Scale the dimensions to the image width.
                return QSize(self.image_list_image_width,
                             int(self.image_list_image_width * height / width))
            return QSize(self.image_list_image_width,
                         self.image_list_image_width)

    def get_file_paths(self, directory_path: Path) -> set[Path]:
        """
        Recursively get all file paths in a directory, including those in
        subdirectories.
        """
        file_paths = set()
        for path in directory_path.iterdir():
            if path.is_file():
                file_paths.add(path)
            elif path.is_dir():
                file_paths.update(self.get_file_paths(path))
        return file_paths

    def load_directory(self, directory_path: Path):
        self.images.clear()
        file_paths = self.get_file_paths(directory_path)
        text_file_paths = {path for path in file_paths
                           if path.suffix == '.txt'}
        image_paths = file_paths - text_file_paths
        for image_path in image_paths:
            try:
                dimensions = imagesize.get(image_path)
            except ValueError:
                dimensions = None
            tags = []
            text_file_path = image_path.with_suffix('.txt')
            if text_file_path in text_file_paths:
                caption = text_file_path.read_text()
                if caption:
                    tags = caption.split(self.separator)
                    tags = [tag.strip() for tag in tags]
                    tags = [tag for tag in tags if tag]
            image = Image(image_path, dimensions, tags)
            self.images.append(image)
        self.images.sort(key=lambda image_: image_.path)
        self.modelReset.emit()

    def write_image_tags_to_disk(self, image: Image):
        try:
            image.path.with_suffix('.txt').write_text(
                self.separator.join(image.tags))
        except OSError:
            error_message_box = QMessageBox()
            error_message_box.setWindowTitle('Error')
            error_message_box.setIcon(QMessageBox.Icon.Critical)
            error_message_box.setText(f'An error occurred while saving the '
                                      f'tags for {image.path.name}.')
            error_message_box.exec()

    def update_image_tags(self, image_index: QModelIndex, tags: list[str]):
        image: Image = self.data(image_index, Qt.UserRole)
        if image.tags == tags:
            return
        image.tags = tags
        self.dataChanged.emit(image_index, image_index)
        self.write_image_tags_to_disk(image)

    def remove_duplicate_tags(self) -> int:
        """
        Remove duplicate tags for each image. Return the number of removed
        tags.
        """
        changed_image_indices = []
        removed_tag_count = 0
        for image_index, image in enumerate(self.images):
            tag_count = len(image.tags)
            unique_tag_count = len(set(image.tags))
            if tag_count == unique_tag_count:
                continue
            changed_image_indices.append(image_index)
            removed_tag_count += tag_count - unique_tag_count
            # Use a dictionary instead of a set to preserve the order.
            image.tags = list(dict.fromkeys(image.tags))
            self.write_image_tags_to_disk(image)
        if changed_image_indices:
            self.dataChanged.emit(self.index(changed_image_indices[0]),
                                  self.index(changed_image_indices[-1]))
        return removed_tag_count

    def sort_tags_alphabetically(self, do_not_reorder_first_tag: bool):
        """Sort the tags for each image in alphabetical order."""
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if len(image.tags) < 2:
                continue
            old_caption = self.separator.join(image.tags)
            if do_not_reorder_first_tag:
                first_tag = image.tags[0]
                image.tags = [first_tag] + sorted(image.tags[1:])
            else:
                image.tags.sort()
            new_caption = self.separator.join(image.tags)
            if new_caption != old_caption:
                changed_image_indices.append(image_index)
                self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))

    def sort_tags_by_frequency(self, tag_counter: Counter,
                               do_not_reorder_first_tag: bool):
        """
        Sort the tags for each image by the total number of times a tag appears
        across all images.
        """
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if len(image.tags) < 2:
                continue
            old_caption = self.separator.join(image.tags)
            if do_not_reorder_first_tag:
                first_tag = image.tags[0]
                image.tags = [first_tag] + sorted(
                    image.tags[1:], key=lambda tag: tag_counter[tag],
                    reverse=True)
            else:
                image.tags.sort(key=lambda tag: tag_counter[tag], reverse=True)
            new_caption = self.separator.join(image.tags)
            if new_caption != old_caption:
                changed_image_indices.append(image_index)
                self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))

    def shuffle_tags(self, do_not_reorder_first_tag: bool):
        """Shuffle the tags for each image randomly."""
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if len(image.tags) < 2:
                continue
            changed_image_indices.append(image_index)
            if do_not_reorder_first_tag:
                first_tag, *remaining_tags = image.tags
                random.shuffle(remaining_tags)
                image.tags = [first_tag] + remaining_tags
            else:
                random.shuffle(image.tags)
            self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))

    @Slot(str, str)
    def rename_tag(self, old_tag: str, new_tag: str):
        """Rename all instances of a tag in all images."""
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if old_tag in image.tags:
                changed_image_indices.append(image_index)
                image.tags = [new_tag if image_tag == old_tag else image_tag
                              for image_tag in image.tags]
                self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))

    @Slot(str)
    def delete_tag(self, tag: str):
        """Delete all instances of a tag from all images."""
        changed_image_indices = []
        for image_index, image in enumerate(self.images):
            if tag in image.tags:
                changed_image_indices.append(image_index)
                image.tags = [image_tag for image_tag in image.tags
                              if image_tag != tag]
                self.write_image_tags_to_disk(image)
        self.dataChanged.emit(self.index(changed_image_indices[0]),
                              self.index(changed_image_indices[-1]))
