
        @Grab(group='org.apache.poi', module='poi', version='5.2.3')
        @Grab(group='org.apache.poi', module='poi-ooxml', version='5.2.3')
        
        import org.apache.poi.hssf.usermodel.HSSFWorkbook
        import org.apache.poi.xssf.usermodel.XSSFWorkbook
        import java.io.FileInputStream
        import java.io.FileOutputStream
        
        def convertXlsToXlsx(xlsPath, xlsxPath) {
            try {
                println("Leyendo archivo XLS: " + xlsPath)
                def xlsFile = new FileInputStream(xlsPath)
                def workbook = new HSSFWorkbook(xlsFile)
                println("Archivo XLS leído correctamente, hojas: " + workbook.getNumberOfSheets())
                
                def newWorkbook = new XSSFWorkbook()
                
                // Copiar todas las hojas
                workbook.getNumberOfSheets().times { sheetIndex ->
                    def sheet = workbook.getSheetAt(sheetIndex)
                    def newSheet = newWorkbook.createSheet(sheet.getSheetName())
                    
                    println("Copiando hoja: " + sheet.getSheetName())
                    
                    // Copiar todas las filas
                    sheet.iterator().each { row ->
                        def newRow = newSheet.createRow(row.getRowNum())
                        
                        // Copiar todas las celdas
                        row.iterator().each { cell ->
                            def newCell = newRow.createCell(cell.getColumnIndex())
                            
                            // Copiar el valor de la celda según su tipo
                            switch (cell.getCellType()) {
                                case 0: // CELL_TYPE_NUMERIC
                                    newCell.setCellValue(cell.getNumericCellValue())
                                    break
                                case 1: // CELL_TYPE_STRING
                                    newCell.setCellValue(cell.getStringCellValue())
                                    break
                                case 2: // CELL_TYPE_FORMULA
                                    newCell.setCellValue(cell.getCellFormula())
                                    break
                                case 3: // CELL_TYPE_BLANK
                                    // Dejar en blanco
                                    break
                                case 4: // CELL_TYPE_BOOLEAN
                                    newCell.setCellValue(cell.getBooleanCellValue())
                                    break
                                case 5: // CELL_TYPE_ERROR
                                    newCell.setCellValue(cell.getErrorCellValue())
                                    break
                            }
                        }
                    }
                }
                
                println("Guardando archivo XLSX: " + xlsxPath)
                def xlsxFile = new FileOutputStream(xlsxPath)
                newWorkbook.write(xlsxFile)
                xlsxFile.close()
                workbook.close()
                xlsFile.close()
                
                println("Conversión completada exitosamente")
                return true
            } catch (Exception e) {
                println("Error en la conversión: " + e.getMessage())
                e.printStackTrace()
                return false
            }
        }
        
        // Ejecutar la conversión
        args = args as List
        convertXlsToXlsx(args[0], args[1])
        