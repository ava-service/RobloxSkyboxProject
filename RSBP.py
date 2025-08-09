import sys
import os
import shutil
from pathlib import Path
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *
from PIL import Image
import math
from io import BytesIO

vrs = 'r8.9.25-bday'
FACE_NAMES = ['ft', 'bk', 'lf', 'rt', 'up', 'dn']

def _swap_rb_channels(img):
    # Roblox uses BGRA, so swap R & B
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    r, g, b, a = img.split()
    return Image.merge('RGBA', (b, g, r, a))


class SkyboxPreview(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.textures = {}
        self.rot_x = 20
        self.rot_y = -30
        self.last_pos = None
        self.use_spherical_uv = False
        self.subdivide = 20

    def initializeGL(self):
        glEnable(GL_TEXTURE_2D)
        glClearColor(0, 0, 0, 1)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_CULL_FACE)

    def resizeGL(self, w, h):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(60, w / h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        glRotatef(self.rot_x, 1, 0, 0)
        glRotatef(self.rot_y, 0, 1, 0)

        glDepthMask(GL_FALSE)
        glDisable(GL_CULL_FACE)
        self.drawSkybox()
        glEnable(GL_CULL_FACE)
        glDepthMask(GL_TRUE)

    def drawSkybox(self):
        size = 1.0
        vertices = [
            [-size, -size, size],
            [size, -size, size],
            [size, size, size],
            [-size, size, size],
            [-size, -size, -size],
            [size, -size, -size],
            [size, size, -size],
            [-size, size, -size],
        ]

        faces = {
            'ft': ([0, 1, 2, 3], [(0, 0), (1, 0), (1, 1), (0, 1)]),
            'bk': ([5, 4, 7, 6], [(0, 0), (1, 0), (1, 1), (0, 1)]),
            'rt': ([4, 0, 3, 7], [(0, 0), (1, 0), (1, 1), (0, 1)]),
            'lf': ([1, 5, 6, 2], [(0, 0), (1, 0), (1, 1), (0, 1)]),
            'up': ([3, 2, 6, 7], [(0, 0), (1, 0), (1, 1), (0, 1)]),
            'dn': ([4, 5, 1, 0], [(0, 0), (1, 0), (1, 1), (0, 1)]),
        }

        glEnable(GL_TEXTURE_2D)
        glFrontFace(GL_CW)

        for face_name, (verts_idx, _) in faces.items():
            tex_id = self.textures.get(face_name)
            if tex_id:
                glBindTexture(GL_TEXTURE_2D, tex_id)
            else:
                glBindTexture(GL_TEXTURE_2D, 0)

            if self.use_spherical_uv:
                self.drawFaceSpherical(vertices, verts_idx)
            else:
                self.drawFaceFlat(vertices, verts_idx)

        glFrontFace(GL_CCW)

    def drawFaceFlat(self, vertices, verts_idx):
        texcoords = [(0, 0), (1, 0), (1, 1), (0, 1)]
        glBegin(GL_QUADS)
        for vi, (u, v) in zip(verts_idx, texcoords):
            glTexCoord2f(u, v)
            glVertex3f(*vertices[vi])
        glEnd()

    def drawFaceSpherical(self, vertices, verts_idx):
        sub = self.subdivide
        v0 = vertices[verts_idx[0]]
        v1 = vertices[verts_idx[1]]
        v2 = vertices[verts_idx[2]]
        v3 = vertices[verts_idx[3]]

        for i in range(sub):
            t0 = i / sub
            t1 = (i + 1) / sub
            glBegin(GL_TRIANGLE_STRIP)
            for j in range(sub + 1):
                s = j / sub

                pA = self.lerp3D(self.lerp3D(v0, v1, s), self.lerp3D(v3, v2, s), t0)
                pB = self.lerp3D(self.lerp3D(v0, v1, s), self.lerp3D(v3, v2, s), t1)

                uA, vA = self.cubeToSphereUV(pA)
                uB, vB = self.cubeToSphereUV(pB)

                glTexCoord2f(uA, vA)
                glVertex3f(*pA)
                glTexCoord2f(uB, vB)
                glVertex3f(*pB)
            glEnd()

    def lerp3D(self, a, b, t):
        # lerp between points
        return [a[i] + (b[i] - a[i]) * t for i in range(3)]

    def cubeToSphereUV(self, pos):
        # cube coords → spherical UV
        x, y, z = pos
        length = math.sqrt(x*x + y*y + z*z)
        nx, ny, nz = x/length, y/length, z/length

        u = 0.5 + math.atan2(nz, nx) / (2 * math.pi)
        v = 0.5 - math.asin(ny) / math.pi
        return u, v

    def loadTexture(self, face_name, pil_image):
        # upload texture to GPU
        img = pil_image.convert('RGBA')
        img_data = img.tobytes("raw", "RGBA", 0, -1)
        w, h = img.size

        if face_name in self.textures:
            glDeleteTextures([self.textures[face_name]])
        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, img_data)
        self.textures[face_name] = tex_id
        self.update()

    def mousePressEvent(self, event):
        self.last_pos = event.pos()

    def mouseMoveEvent(self, event):
        if self.last_pos:
            dx = event.x() - self.last_pos.x()
            dy = event.y() - self.last_pos.y()
            self.rot_x += dy
            self.rot_y += dx
            self.rot_x = max(min(self.rot_x, 90), -90)
            self.last_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.last_pos = None


class SkyboxGenerator(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Roblox SkyBox Project - ava.service " + vrs)
        self.setMinimumSize(1000, 600)

        self.face_images = {face: None for face in FACE_NAMES}
        self.stretch_image = None

        self.temp_folder = os.path.join(os.getcwd(), "temp_skybox_images")
        os.makedirs(self.temp_folder, exist_ok=True)

        self.initUI()

    def initUI(self):
        main_layout = QtWidgets.QHBoxLayout(self)

        panel = QtWidgets.QFrame()
        panel.setFixedWidth(460)
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)

        panel_layout.addWidget(QtWidgets.QLabel("Skybox Title (folder name):"))
        self.title_input = QtWidgets.QLineEdit()
        panel_layout.addWidget(self.title_input)

        panel_layout.addSpacing(15)

        self.mode_group = QtWidgets.QButtonGroup()
        self.radio_six = QtWidgets.QRadioButton("Six Separate Images (recommended)")
        self.radio_stretch = QtWidgets.QRadioButton("Single Stretch Image")
        self.radio_six.setChecked(True)
        self.mode_group.addButton(self.radio_six)
        self.mode_group.addButton(self.radio_stretch)
        panel_layout.addWidget(self.radio_six)
        panel_layout.addWidget(self.radio_stretch)

        panel_layout.addSpacing(10)

        self.face_inputs = {}
        for face in FACE_NAMES:
            face_label = QtWidgets.QLabel(face.upper())
            face_label.setFixedWidth(25)

            face_path_edit = QtWidgets.QLineEdit()
            face_path_edit.setReadOnly(True)

            browse_btn = QtWidgets.QPushButton("Browse")
            browse_btn.setFixedWidth(55)
            browse_btn.clicked.connect(lambda _, f=face: self.browseFaceImage(f))

            load_tex_btn = QtWidgets.QPushButton("Load .tex")
            load_tex_btn.setFixedWidth(60)
            load_tex_btn.clicked.connect(lambda _, f=face: self.loadTexFile(f))

            rotate_btn = QtWidgets.QPushButton("R")
            rotate_btn.setFixedWidth(20)
            rotate_btn.clicked.connect(lambda _, f=face: self.rotateImage(f))

            flip_btn = QtWidgets.QPushButton("F")
            flip_btn.setFixedWidth(20)
            flip_btn.clicked.connect(lambda _, f=face: self.flipImage(f))

            row_layout = QtWidgets.QHBoxLayout()
            row_layout.addWidget(face_label)
            row_layout.addWidget(rotate_btn)
            row_layout.addWidget(flip_btn)
            row_layout.addWidget(browse_btn)
            row_layout.addWidget(load_tex_btn)
            row_layout.addWidget(face_path_edit)

            panel_layout.addLayout(row_layout)

            self.face_inputs[face] = {
                'path_edit': face_path_edit,
                'browse_btn': browse_btn,
                'load_tex_btn': load_tex_btn,
                'rotate_btn': rotate_btn,
                'flip_btn': flip_btn,
            }

        panel_layout.addSpacing(20)

        panel_layout.addWidget(QtWidgets.QLabel("Single Image to Stretch:"))

        stretch_row = QtWidgets.QHBoxLayout()
        self.stretch_path_edit = QtWidgets.QLineEdit()
        self.stretch_path_edit.setReadOnly(True)
        stretch_row.addWidget(self.stretch_path_edit, 1)

        self.stretch_rotate_btn = QtWidgets.QPushButton("R")
        self.stretch_rotate_btn.setFixedWidth(20)
        self.stretch_rotate_btn.clicked.connect(self.rotateStretchImage)
        stretch_row.addWidget(self.stretch_rotate_btn)

        self.stretch_flip_btn = QtWidgets.QPushButton("F")
        self.stretch_flip_btn.setFixedWidth(20)
        self.stretch_flip_btn.clicked.connect(self.flipStretchImage)
        stretch_row.addWidget(self.stretch_flip_btn)

        self.btn_browse_stretch = QtWidgets.QPushButton("Browse Stretch Image")
        self.btn_browse_stretch.clicked.connect(self.browseStretchImage)
        stretch_row.addWidget(self.btn_browse_stretch)

        panel_layout.addLayout(stretch_row)

        panel_layout.addSpacing(20)

        self.btn_bulk_import = QtWidgets.QPushButton("Bulk Import Images")
        self.btn_bulk_import.clicked.connect(self.bulkImportImages)
        panel_layout.addWidget(self.btn_bulk_import)

        panel_layout.addSpacing(10)

        self.btn_generate = QtWidgets.QPushButton("Generate Skybox")
        self.btn_generate.clicked.connect(self.generateSkybox)
        panel_layout.addWidget(self.btn_generate)

        panel_layout.addStretch()

        main_layout.addWidget(panel)

        self.preview = SkyboxPreview()
        main_layout.addWidget(self.preview, 1)

        self.mode_group.buttonClicked.connect(self.updateMode)
        self.updateMode()

    def updateMode(self):
        six_mode = self.radio_six.isChecked()
        for face in FACE_NAMES:
            self.face_inputs[face]['path_edit'].setEnabled(six_mode)
            self.face_inputs[face]['browse_btn'].setEnabled(six_mode)
            self.face_inputs[face]['load_tex_btn'].setEnabled(six_mode)
            self.face_inputs[face]['rotate_btn'].setEnabled(six_mode)
            self.face_inputs[face]['flip_btn'].setEnabled(six_mode)

        self.stretch_path_edit.setEnabled(not six_mode)
        self.btn_browse_stretch.setEnabled(not six_mode)
        self.stretch_rotate_btn.setEnabled(not six_mode)
        self.stretch_flip_btn.setEnabled(not six_mode)

        self.preview.textures.clear()
        self.preview.use_spherical_uv = not six_mode
        self.preview.update()

    def copyToTemp(self, face, source_path):
        dest_path = os.path.join(self.temp_folder, f"{face}.png")
        try:
            img = Image.open(source_path)
            img = img.resize((512, 512), Image.LANCZOS)
            img.save(dest_path, format='PNG')
            return dest_path
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Copy Error", f"Failed copying image to temp:\n{str(e)}")
            return None

    def overwriteTempImage(self, face):
        if self.face_images[face]:
            dest_path = os.path.join(self.temp_folder, f"{face}.png")
            try:
                self.face_images[face].save(dest_path, format='PNG')
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Save Error", f"Failed saving updated image to temp:\n{str(e)}")

    def overwriteTempStretch(self):
        if self.stretch_image:
            dest_path = os.path.join(self.temp_folder, "stretch.png")
            try:
                self.stretch_image.save(dest_path, format='PNG')
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Save Error", f"Failed saving updated stretch image to temp:\n{str(e)}")

    def browseFaceImage(self, face):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, f"Select image for {face.upper()}", "",
                                                     "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff);;All Files (*)")
        if path:
            temp_path = self.copyToTemp(face, path)
            if temp_path:
                img = Image.open(temp_path)
                self.face_images[face] = img
                self.face_inputs[face]['path_edit'].setText(temp_path)
                self.preview.loadTexture(face, img)

    def loadTexFile(self, face):
        # Implement .tex loading if needed
        pass

    def rotateImage(self, face):
        if self.face_images[face]:
            self.face_images[face] = self.face_images[face].rotate(-90, expand=True)
            self.overwriteTempImage(face)
            self.preview.loadTexture(face, self.face_images[face])

    def flipImage(self, face):
        if self.face_images[face]:
            self.face_images[face] = self.face_images[face].transpose(Image.FLIP_LEFT_RIGHT)
            self.overwriteTempImage(face)
            self.preview.loadTexture(face, self.face_images[face])

    def browseStretchImage(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select stretch image", "",
                                                     "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff);;All Files (*)")
        if path:
            img = Image.open(path).resize((512, 512), Image.LANCZOS)
            self.stretch_image = img
            temp_path = os.path.join(self.temp_folder, "stretch.png")
            img.save(temp_path, format='PNG')
            self.stretch_path_edit.setText(temp_path)
            self.preview.loadTexture('stretch', img)

    def rotateStretchImage(self):
        if self.stretch_image:
            self.stretch_image = self.stretch_image.rotate(-90, expand=True)
            self.overwriteTempStretch()
            self.preview.loadTexture('stretch', self.stretch_image)

    def flipStretchImage(self):
        if self.stretch_image:
            self.stretch_image = self.stretch_image.transpose(Image.FLIP_LEFT_RIGHT)
            self.overwriteTempStretch()
            self.preview.loadTexture('stretch', self.stretch_image)

    def bulkImportImages(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder with images")
        if not folder:
            return

        # Load images by filename endings like ft, bk etc.
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if not os.path.isfile(fpath):
                continue
            for face in FACE_NAMES:
                if fname.lower().endswith(face + ".png"):
                    temp_path = self.copyToTemp(face, fpath)
                    if temp_path:
                        img = Image.open(temp_path)
                        self.face_images[face] = img
                        self.face_inputs[face]['path_edit'].setText(temp_path)
                        self.preview.loadTexture(face, img)
                    break

    def generateSkybox(self):
        title = self.title_input.text().strip()
        if not title:
            QtWidgets.QMessageBox.warning(self, "Missing Title", "You need to enter a folder name!")
            return

        output_folder = os.path.join(os.getcwd(), title)
        if os.path.exists(output_folder):
            reply = QtWidgets.QMessageBox.question(self, "Overwrite?", 
                        f"Folder '{title}' exists. Overwrite?", 
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if reply != QtWidgets.QMessageBox.Yes:
                return
            shutil.rmtree(output_folder)

        os.makedirs(output_folder)

        if self.radio_six.isChecked():
            # Six images mode: save faces as sky512_[face].png + generate .tex
            for face in FACE_NAMES:
                img = self.face_images.get(face)
                if not img:
                    QtWidgets.QMessageBox.warning(self, "Missing Image", f"Face '{face}' is missing!")
                    return
                png_path = os.path.join(output_folder, f"sky512_{face}.png")
                img.save(png_path, format='PNG')

                # save .tex files for Roblox - swap RB channels and save with specific encoding
                tex_path = os.path.join(output_folder, f"sky512_{face}.tex")
                tex_img = _swap_rb_channels(img)
                tex_img.save(tex_path, format='PNG')
        else:
            # Single stretch mode - save stretched images for all faces from one image
            if not self.stretch_image:
                QtWidgets.QMessageBox.warning(self, "No Stretch Image", "Load a stretch image first!")
                return

            # Just save the stretch image under all faces for simplicity
            for face in FACE_NAMES:
                png_path = os.path.join(output_folder, f"sky512_{face}.png")
                self.stretch_image.save(png_path, format='PNG')
                tex_path = os.path.join(output_folder, f"sky512_{face}.tex")
                tex_img = _swap_rb_channels(self.stretch_image)
                tex_img.save(tex_path, format='PNG')

        QtWidgets.QMessageBox.information(self, "Done", f"Skybox generated in '{output_folder}'")

        # Cleanup temp folder if needed
        shutil.rmtree(self.temp_folder, ignore_errors=True)
        os.makedirs(self.temp_folder, exist_ok=True)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = SkyboxGenerator()
    window.show()
    sys.exit(app.exec_())
