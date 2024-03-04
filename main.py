import sys
import praw
import csv
import os
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLineEdit,
    QPushButton,
    QLabel,
    QSpinBox,
    QFileDialog,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QMessageBox
    )
from PySide6.QtCore import QThread, QObject, Signal, Slot

# Initialize PRAW with your client credentials
reddit = praw.Reddit(
    client_id='Your Client ID here',
    client_secret='Your Client Secret here',
    user_agent='Your User Agent here'
)

def sanitize_title(title):
    """Sanitize the title to create a valid filename."""
    return re.sub(r'[\\/*?:"<>|]', "", title)

def save_comments_to_csv(post_url, limit, directory, save_all):
    submission = reddit.submission(url=post_url)
    submission.comments.replace_more(limit=None)
    
    # Decide which comments to iterate over based on the save_all flag
    if save_all:
        comments_to_save = submission.comments.list()
    else:
        comments_to_save = submission.comments.list()[:limit]
    comments = [(comment.score, len(comment.replies), comment.body) for comment in comments_to_save]
    total_top_level_comments = len(submission.comments)  # Get the total number of top-level comments
    
    # Sort comments by points in descending order
    comments.sort(key=lambda x: x[0], reverse=True)

    csv_filename = sanitize_title(submission.title) + '.csv'
    csv_path = os.path.join(directory, csv_filename)  # Use os.path.join to form the full file path
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        writer.writerow(['Points', 'Replies', 'Comment'])
        for comment in comments:
            writer.writerow(comment)
            
    return total_top_level_comments  # Return the total number of top-level comments

class RedditThread(QObject):
    finished = Signal()
    error = Signal(str)
    total_comments_signal = Signal(int)  # New signal for total comments
    
    def __init__(self, url, limit, directory, save_all):
        super().__init__()
        self.url = url
        self.limit = limit
        self.directory = directory
        self.save_all = save_all

    def run(self):
        try:
            # Pass the save_all attribute to the function
            total_comments = save_comments_to_csv(self.url, self.limit, self.directory, self.save_all)
            self.total_comments_signal.emit(total_comments)  # Emit total comments signal
        except Exception as e:
            self.error.emit(str(e))
        self.finished.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Top Level Reddit Comments")
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Widgets for user input
        self.url_input = QLineEdit()
        self.limit_input = QSpinBox()
        self.limit_input.setRange(1, 1000)
        self.save_button = QPushButton("Save Comments")
        self.browse_button = QPushButton("Choose Save Location")

        # Widgets for output and feedback
        self.status_label = QLabel("Ready")
        
        # Checkbox for saving all top-level comments
        self.save_all_checkbox = QCheckBox("Save all top-level comments")

        # Layout
        layout = QVBoxLayout()
        link_layout = QHBoxLayout()
        input_layout = QHBoxLayout()
        link_layout.addWidget(QLabel("Reddit Post URL:"))
        link_layout.addWidget(self.url_input)
        input_layout.addWidget(QLabel("Comment Limit:"))
        input_layout.addWidget(self.limit_input)
        input_layout.addWidget(self.save_all_checkbox)  # Add the checkbox to your layout
        layout.addLayout(link_layout)
        layout.addLayout(input_layout)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.browse_button)
        
        layout.addLayout(button_layout)
        layout.addWidget(self.status_label)
        self.central_widget.setLayout(layout)

        # Connect signals to slots
        self.save_button.clicked.connect(self.save_comments)
        self.browse_button.clicked.connect(self.choose_save_location)

        # Initialize save directory to the current script directory
        self.default_save_directory = os.path.dirname(os.path.realpath(__file__))
        self.save_directory = self.load_default_directory()  # Load the last saved default directory
        if not self.save_directory:
            self.save_directory = self.default_save_directory

        self.status_label.setText(f"Save location: {self.save_directory}")
        
    def confirm_save_all(self, total_comments):
        reply = QMessageBox.question(self, 'Confirm Save All', 
                                     f'The post has {total_comments} top-level comments. Do you wish to proceed?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def save_comments(self):
        # Only fetch comments count and show confirmation if "Save all" is selected
        if self.save_all_checkbox.isChecked():
            # Fetch the total number of comments to show in the confirmation dialog
            submission = reddit.submission(url=self.url_input.text())
            submission.comments.replace_more(limit=0)
            total_comments = len(submission.comments)
            
            if not self.confirm_save_all(total_comments):
                self.status_label.setText("Save cancelled by user.")
                return
            

        # Proceed with setting up and starting the worker thread if not cancelled
        self.thread = QThread()
        self.worker = RedditThread(self.url_input.text(), self.limit_input.value(), self.save_directory, self.save_all_checkbox.isChecked())
        self.setup_worker_thread()

    def setup_worker_thread(self):
        # Move the worker to the thread
        self.worker.moveToThread(self.thread)

        # Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.error.connect(self.display_error)
        self.worker.total_comments_signal.connect(self.display_total_comments)
        
        # Start the thread
        self.thread.start()

    @Slot(str)
    def display_error(self, message):
        self.status_label.setText(f"Error: {message}")

    @Slot(int)
    def display_total_comments(self, total_comments):
        self.status_label.setText(f"Total top-level comments: {total_comments}")
    
    def save_default_directory(self):
        with open('default_dir.txt', 'w') as file:
            file.write(self.save_directory)

    def load_default_directory(self):
        if os.path.exists('default_dir.txt'):
            with open('default_dir.txt', 'r') as file:
                return file.read().strip()
        return None

    def choose_save_location(self):
        directory = QFileDialog.getExistingDirectory(self, "Choose Save Location", self.default_save_directory, options=QFileDialog.ShowDirsOnly)
        if directory:
            self.save_directory = directory
            self.save_default_directory()  # Save the new default directory
            self.status_label.setText(f"Save location set to: {directory}")
        else:
            self.status_label.setText(f"No directory selected. Using: {self.save_directory}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())